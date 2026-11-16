"""Generic, location-independent Areas of Interest (AOI).

An AOI is *not* tied to a river, a station table or a country. It accepts either a
GeoJSON polygon supplied by a map, or a point plus a configurable buffer. A stable
``aoi_key`` derived from the canonical geometry lets stored observations be
retrieved later without depending on any UI row id.

All geometries are WGS84 (EPSG:4326) lon/lat, GeoJSON axis order.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

EARTH_RADIUS_M = 6371008.8
MIN_BUFFER_M = 50.0
MAX_BUFFER_M = 50_000.0
DEFAULT_BUFFER_M = 300.0
DEFAULT_STEPS = 64
GEOMETRY_PRECISION = 7
MAX_POLYGON_POINTS = 5_000
KIND_POINT_BUFFER = "point_buffer"
KIND_POLYGON = "polygon"


class AOIValidationError(ValueError):
    """Raised when an AOI cannot be used for satellite retrieval."""


def validate_point(latitude: Any, longitude: Any) -> Tuple[float, float]:
    """Validate and normalise a WGS84 point in decimal degrees."""
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError) as error:
        raise AOIValidationError(
            "Latitude and longitude are required as WGS84 decimal degrees."
        ) from error
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise AOIValidationError("Latitude and longitude must be finite numbers.")
    if not -90.0 <= lat <= 90.0:
        raise AOIValidationError("Latitude must be between -90 and 90 degrees.")
    if not -180.0 <= lon <= 180.0:
        raise AOIValidationError("Longitude must be between -180 and 180 degrees.")
    return lat, lon


def validate_buffer(buffer_m: Any = None) -> float:
    """Validate the point buffer radius in metres."""
    value = DEFAULT_BUFFER_M if buffer_m is None else buffer_m
    try:
        metres = float(value)
    except (TypeError, ValueError) as error:
        raise AOIValidationError("Buffer must be a number of metres.") from error
    if not math.isfinite(metres):
        raise AOIValidationError("Buffer must be a finite number of metres.")
    if metres < MIN_BUFFER_M:
        raise AOIValidationError(
            f"Buffer must be at least {int(MIN_BUFFER_M)} m; smaller areas are below one "
            "Sentinel-2 pixel footprint and cannot support a water-area estimate."
        )
    if metres > MAX_BUFFER_M:
        raise AOIValidationError(
            f"Buffer must be at most {int(MAX_BUFFER_M)} m. Use a polygon for larger reaches "
            "or waterbodies."
        )
    return metres


def _destination(latitude: float, longitude: float, distance_m: float, bearing_deg: float) -> Tuple[float, float]:
    """Great-circle destination point for a bearing and distance."""
    angular = distance_m / EARTH_RADIUS_M
    bearing = math.radians(bearing_deg)
    phi1 = math.radians(latitude)
    lambda1 = math.radians(longitude)

    sin_phi2 = math.sin(phi1) * math.cos(angular) + math.cos(phi1) * math.sin(angular) * math.cos(bearing)
    phi2 = math.asin(max(-1.0, min(1.0, sin_phi2)))
    lambda2 = lambda1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(phi1),
        math.cos(angular) - math.sin(phi1) * sin_phi2,
    )
    lon2 = (math.degrees(lambda2) + 540.0) % 360.0 - 180.0
    return math.degrees(phi2), lon2


def buffer_polygon(
    latitude: Any,
    longitude: Any,
    buffer_m: Any = None,
    steps: int = DEFAULT_STEPS,
) -> Dict[str, Any]:
    """Build a geodesic circular polygon around a point (GeoJSON Polygon)."""
    lat, lon = validate_point(latitude, longitude)
    metres = validate_buffer(buffer_m)
    if steps < 8:
        raise AOIValidationError("A buffer polygon needs at least 8 vertices.")

    ring: List[List[float]] = []
    for index in range(steps):
        bearing = 360.0 * index / steps
        point_lat, point_lon = _destination(lat, lon, metres, bearing)
        ring.append([round(point_lon, GEOMETRY_PRECISION), round(point_lat, GEOMETRY_PRECISION)])
    ring.append(list(ring[0]))

    return {
        "type": "Polygon",
        "coordinates": [ring],
        # Custom (non-GeoJSON) hint retained for display only; ignored by geometry readers.
        "properties": {
            "kind": KIND_POINT_BUFFER,
            "centre": [round(lon, GEOMETRY_PRECISION), round(lat, GEOMETRY_PRECISION)],
            "buffer_m": metres,
        },
    }


def _validate_ring(ring: Any, label: str) -> List[List[float]]:
    if not isinstance(ring, (list, tuple)) or len(ring) < 4:
        raise AOIValidationError(f"{label} must contain at least four positions and be closed.")
    if len(ring) > MAX_POLYGON_POINTS:
        raise AOIValidationError(f"{label} has too many vertices (limit {MAX_POLYGON_POINTS}).")

    cleaned: List[List[float]] = []
    for position in ring:
        if not isinstance(position, (list, tuple)) or len(position) < 2:
            raise AOIValidationError(f"{label} contains a position without longitude and latitude.")
        lat, lon = validate_point(position[1], position[0])
        cleaned.append([round(lon, GEOMETRY_PRECISION), round(lat, GEOMETRY_PRECISION)])

    if cleaned[0] != cleaned[-1]:
        raise AOIValidationError(f"{label} must be closed: the first and last positions must match.")
    if len({tuple(point) for point in cleaned[:-1]}) < 3:
        raise AOIValidationError(f"{label} needs at least three distinct vertices.")
    return cleaned


def validate_polygon(geometry: Any) -> Dict[str, Any]:
    """Validate a GeoJSON Polygon (or single-part MultiPolygon) and normalise it."""
    if not isinstance(geometry, dict):
        raise AOIValidationError("Geometry must be a GeoJSON object.")

    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if kind == "MultiPolygon":
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 1:
            raise AOIValidationError(
                "Only a single-part MultiPolygon is supported; supply one Polygon per AOI."
            )
        coordinates = coordinates[0]
        kind = "Polygon"

    if kind != "Polygon":
        raise AOIValidationError("Geometry type must be 'Polygon' (or a single-part 'MultiPolygon').")
    if not isinstance(coordinates, (list, tuple)) or not coordinates:
        raise AOIValidationError("Polygon coordinates must be a non-empty ring list.")

    exterior = _validate_ring(coordinates[0], "Polygon exterior ring")
    holes: List[List[List[float]]] = []
    for index, hole in enumerate(coordinates[1:], start=1):
        holes.append(_validate_ring(hole, f"Polygon interior ring {index}"))

    normalised = {"type": "Polygon", "coordinates": [exterior, *holes]}
    properties = geometry.get("properties")
    if isinstance(properties, dict) and properties:
        normalised["properties"] = properties

    area = polygon_area_km2(normalised)
    if area <= 0.0:
        raise AOIValidationError("Polygon encloses no measurable area.")
    return normalised


def exterior_ring(geometry: Dict[str, Any]) -> Sequence[Sequence[float]]:
    return geometry["coordinates"][0]


def polygon_area_km2(geometry: Dict[str, Any]) -> float:
    """Spherical-excess area of the exterior ring, in square kilometres.

    Holes are ignored: an AOI describes the retrieval footprint, and Sentinel-2
    statistics are computed per pixel over that footprint rather than by subtracting
    islands. The value is metadata, not a water-area measurement.
    """
    ring = exterior_ring(geometry)
    if len(ring) < 4:
        return 0.0
    total = 0.0
    for index in range(len(ring) - 1):
        lon1, lat1 = math.radians(ring[index][0]), math.radians(ring[index][1])
        lon2, lat2 = math.radians(ring[index + 1][0]), math.radians(ring[index + 1][1])
        total += (lon2 - lon1) * (2.0 + math.sin(lat1) + math.sin(lat2))
    area_m2 = abs(total) * (EARTH_RADIUS_M ** 2) / 2.0
    return round(area_m2 / 1_000_000.0, 6)


def polygon_centroid(geometry: Dict[str, Any]) -> Tuple[float, float]:
    """Vertex-mean centroid of the exterior ring, used only for display."""
    ring = exterior_ring(geometry)[:-1]
    if not ring:
        raise AOIValidationError("Polygon has no vertices.")
    lon = sum(point[0] for point in ring) / len(ring)
    lat = sum(point[1] for point in ring) / len(ring)
    return lat, lon


def canonical_geometry(geometry: Dict[str, Any]) -> str:
    """Deterministic JSON for hashing (key order fixed, no whitespace)."""
    payload = {
        "type": "Polygon",
        "coordinates": [
            [[round(float(point[0]), GEOMETRY_PRECISION), round(float(point[1]), GEOMETRY_PRECISION)] for point in ring]
            for ring in geometry["coordinates"]
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def aoi_key(geometry: Dict[str, Any], buffer_m: Optional[float] = None) -> str:
    """Stable identifier for an AOI: same geometry always yields the same key."""
    buffer_component = "" if buffer_m is None else f"|buffer={float(buffer_m):.3f}"
    digest = hashlib.sha256((canonical_geometry(geometry) + buffer_component).encode("utf-8"))
    return digest.hexdigest()


def build_aoi(
    *,
    name: Optional[str],
    latitude: Any = None,
    longitude: Any = None,
    buffer_m: Any = None,
    geometry: Any = None,
    station_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve user input into a validated AOI description.

    Supply either a GeoJSON ``geometry`` or a ``latitude``/``longitude`` point.
    A point is expanded by ``buffer_m`` (default 300 m) into a circular polygon.
    Missing coordinates are never invented.
    """
    label = (name or "").strip() or None
    has_point = latitude is not None and longitude is not None

    if geometry is not None:
        polygon = validate_polygon(geometry)
        try:
            lat, lon = polygon_centroid(polygon)
        except AOIValidationError:
            lat, lon = (None, None)
        used_buffer = None
        kind = KIND_POLYGON
    else:
        if not has_point:
            raise AOIValidationError(
                "Provide a GeoJSON polygon, or a latitude and longitude to build a buffered point AOI."
            )
        lat, lon = validate_point(latitude, longitude)
        used_buffer = validate_buffer(buffer_m)
        polygon = buffer_polygon(lat, lon, used_buffer)
        kind = KIND_POINT_BUFFER

    return {
        "name": label or "Unnamed area of interest",
        "kind": kind,
        "latitude": None if lat is None else round(float(lat), GEOMETRY_PRECISION),
        "longitude": None if lon is None else round(float(lon), GEOMETRY_PRECISION),
        "buffer_m": used_buffer,
        "geometry": polygon,
        "area_km2": polygon_area_km2(polygon),
        "station_ref": (station_ref or None) or None,
        "aoi_key": aoi_key(polygon, used_buffer),
    }
