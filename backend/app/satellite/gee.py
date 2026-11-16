"""Google Earth Engine transport for Sentinel-2 surface reflectance.

Design rules enforced here:

- Earth Engine is imported **lazily**. The FastAPI application starts and serves every
  other route even when ``earthengine-api`` is absent or unconfigured.
- ``ee.Authenticate()`` is never called: initialisation must never trigger an
  interactive browser/console prompt from a server process.
- Every failure is raised as :class:`GeeError` with an actionable message. There is no
  silent fallback to fixtures or dummy values anywhere in this module.
- Metric reductions always run over a locally-derived projected CRS (a UTM zone, or a polar
  stereographic for extreme latitudes) computed from the AOI centroid. This avoids the
  cosine(lat) distortion that comes from requesting ``scale=10`` in WGS84 and keeps
  ``pixelArea`` honest for the water-area estimate.
"""

from __future__ import annotations

import math
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import settings
from . import indices

EARTHENGINE_SCOPE = "https://www.googleapis.com/auth/earthengine"


def _utm_crs(longitude: float, latitude: float) -> str:
    """Return a projected CRS for the AOI footprint: a local UTM zone, or north-polar
    stereographic/over the poles.

    Chosen once per AOI from a representative point (centroid-ish, or the first provided
    coordinate). Used for ``reduceRegion`` so scale is metres and pixelArea is square
    metres of the imagery. This keeps the sentinel-2 10 m grid undistorted and avoids the
    cosine(lat) bias of WGS84/EPSG:4326 with a nominal scale.

    near a zone boundary the reported area stays correct metre-for-metre; aligning every
    monthly composite to one zone also gives sensible but not perfect edge pixels near the
    boundary.
    """
    # Normalise into [-180, 180) so a longitude slipped past the antimeridian still lands in
    # the correct zone instead of being clamped into the wrong one.
    lon = ((float(longitude) + 180.0) % 360.0) - 180.0
    lat = float(latitude)

    if lat >= 84.0:
        return "EPSG:3995"          # WGS 84 / ArcticPolarStereographic
    if lat <= -80.0:
        return "EPSG:3031"          # WGS 84 / AntarcticPolarStereographic

    zone = max(1, min(60, int(math.floor((lon + 180.0) / 6.0) + 1)))
    if lat >= 0:
        return f"EPSG:326{zone:02d}"      # WGS 84 / UTM zone N
    return f"EPSG:327{zone:02d}"          # WGS 84 / UTM zone S


def _representative_point(geometry: Dict[str, Any]) -> Tuple[float, float]:
    """Centroid longitude/latitude for the AOI, guaranteed finite.

    Works for GeoJSON points/lines/polygons (single- or multi-ring) as well as the flat
    [lon, lat] pairs the service layer sends for buffer-based AOIs.
    """
    if not geometry:
        raise ValueError("geometry must not be empty")

    pairs: list[tuple[float, float]] = []

    def _collect(node, depth=0):
        if isinstance(node, (int, float)):
            return
        if isinstance(node, list) and node:
            if depth == 2 and len(node) >= 2 and isinstance(node[0], (int, float)) and isinstance(node[1], (int, float)):
                pairs.append((float(node[0]), float(node[1])))
                return
            for sub in node:
                _collect(sub, depth + 1)

    if isinstance(geometry, dict) and "coordinates" in geometry:
        _collect(geometry["coordinates"])
    elif (
        isinstance(geometry, dict)
        and "geom" in geometry
        and isinstance(geometry["geom"], dict)
        and "coordinates" in geometry["geom"]
    ):
        _collect(geometry["geom"]["coordinates"])
    else:
        _collect(geometry)

    if not pairs:
        raise ValueError(f"geometry has no usable coordinates: {geometry!r}")

    lon0 = sum(p[0] for p in pairs) / len(pairs)
    lat0 = sum(p[1] for p in pairs) / len(pairs)
    if not (-180.0 <= float(lon0) <= 180.0 and -90.0 <= float(lat0) <= 90.0):
        raise ValueError(f"aoi centroid out of range: ({lon0}, {lat0})")

    return float(lon0), float(lat0)


class GeeError(RuntimeError):
    """Base class for Earth Engine problems."""


class GeeUnavailable(GeeError):
    """Configuration or authentication is missing/broken (maps to HTTP 503)."""


class GeeQueryError(GeeError):
    """A query was rejected or failed at the Earth Engine side (maps to HTTP 502)."""


_lock = threading.RLock()
_state: Dict[str, Any] = {
    "initialised": False,
    "mode": None,
    "error": None,
}

PACKAGE_HINT = (
    "Install the Earth Engine Python API into the backend environment: "
    "python -m pip install -r backend/requirements.txt"
)

AUTH_HINT = (
    "Authenticate with Earth Engine either by setting GOOGLE_APPLICATION_CREDENTIALS to a "
    "service-account JSON key authorised for Earth Engine, or by running "
    "`earthengine authenticate` once as the developer account that owns the project. "
    "Then set GEE_PROJECT_ID in backend/.env and restart the backend."
)


def _credentials_path() -> str:
    return (settings.GOOGLE_APPLICATION_CREDENTIALS or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "") or "").strip()


def status() -> Dict[str, Any]:
    """Credential-free readiness report. Never returns secret values."""
    try:
        import ee  # noqa: F401

        package_installed = True
    except Exception:  # pragma: no cover - depends on environment
        package_installed = False

    credentials_path = _credentials_path()
    return {
        "package_installed": package_installed,
        "project_configured": bool((settings.GEE_PROJECT_ID or "").strip()),
        "credentials_file_configured": bool(credentials_path),
        "credentials_file_present": bool(credentials_path) and os.path.isfile(credentials_path),
        "credentials_mode": _state["mode"],
        "initialised": bool(_state["initialised"]),
        "last_error": _state["error"],
        "collection": settings.SATELLITE_COLLECTION,
        "algorithm": indices.ALGORITHM,
        "algorithm_version": indices.ALGORITHM_VERSION,
        "install_hint": None if package_installed else PACKAGE_HINT,
        "auth_hint": None if _state["initialised"] else AUTH_HINT,
    }


def ensure_ready() -> Dict[str, Any]:
    """Initialise Earth Engine now, surfacing configuration/auth failures to the caller.

    Route handlers call this before queuing work so a missing project, absent package or
    broken credentials produce an actionable HTTP error instead of a failed job.
    """
    _initialize()
    return status()


def reset_for_tests() -> None:
    """Clear cached initialisation state (used by unit tests only)."""
    with _lock:
        _state.update({"initialised": False, "mode": None, "error": None})


def _initialize() -> Any:
    """Initialise Earth Engine once per process and return the module."""
    with _lock:
        if _state["initialised"]:
            import ee

            return ee

        # Configuration is checked before the import so the most actionable problem is
        # reported first: an unset project is a five-second fix, a missing package is not.
        project = (settings.GEE_PROJECT_ID or "").strip()
        if not project:
            _state["error"] = "GEE_PROJECT_ID is not configured."
            raise GeeUnavailable(
                "GEE_PROJECT_ID is not configured, so Earth Engine queries cannot be sent. "
                "Set GEE_PROJECT_ID to the Google Cloud project that has the Earth Engine API "
                f"enabled. {AUTH_HINT}"
            )

        # A configured-but-missing key file is also a configuration error, and is reported
        # before the package check for the same reason.
        credentials_path = _credentials_path()
        if credentials_path and not os.path.isfile(credentials_path):
            _state["error"] = "GOOGLE_APPLICATION_CREDENTIALS points at a missing file."
            raise GeeUnavailable(
                "GOOGLE_APPLICATION_CREDENTIALS is set but no file exists at that path. "
                "Point it at a service-account JSON key stored outside version control."
            )

        try:
            import ee
        except ImportError as error:
            _state["error"] = "earthengine-api is not installed."
            raise GeeUnavailable(
                "The Google Earth Engine Python API is not installed in the backend "
                f"environment. {PACKAGE_HINT}"
            ) from error

        try:
            if credentials_path:
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path, scopes=[EARTHENGINE_SCOPE]
                )
                ee.Initialize(credentials=credentials, project=project)
                mode = "service_account"
            else:
                # Uses Application Default Credentials: a service account via
                # GOOGLE_APPLICATION_CREDENTIALS-less metadata environment, workload
                # identity, or the refresh token written by `earthengine authenticate`.
                ee.Initialize(project=project)
                mode = "application_default"
        except GeeUnavailable:
            raise
        except Exception as error:  # noqa: BLE001 - surface any backend auth failure
            _state["error"] = f"{type(error).__name__}: {error}"
            raise GeeUnavailable(
                "Google Earth Engine could not be initialised for project "
                f"'{project}' ({type(error).__name__}). {AUTH_HINT}"
            ) from error

        _state.update({"initialised": True, "mode": mode, "error": None})
        return ee


def _reduce_value(
    image: Any,
    reducer: Any,
    region: Any,
    band: Optional[str] = None,
    target_crs: Optional[str] = None,
) -> Optional[float]:
    target = image if band is None else image.select(band)
    values = target.reduceRegion(
        reducer=reducer,
        geometry=region,
        scale=indices.NATIVE_PIXEL_SIZE_M,
        crs=target_crs,
        maxPixels=1_000_000_000,
        bestEffort=False,
        tileScale=4,
    ).getInfo() or {}
    for value in values.values():
        if value is not None:
            return float(value)
    return None


def monthly_ndwi(
    geometry: Dict[str, Any],
    month: str,
    *,
    ndwi_threshold: float,
    max_cloud_pct: int,
) -> Dict[str, Any]:
    """Compute one month of Sentinel-2 NDWI statistics over an AOI polygon.

    Mirrors :mod:`backend.app.satellite.indices` exactly:

    - scenes filtered by AOI bounds, month, and per-scene cloud percentage
    - SCL classes for cloud, cloud shadow, cirrus, snow and no-data excluded per pixel
    - NDWI = (B3 - B8) / (B3 + B8) on surface reflectance
    - per-pixel **median** composite across the month's valid scenes
    - water area = sum(pixelArea) where NDWI >= threshold, on a fixed 10 m grid
    """
    ee = _initialize()
    threshold = float(ndwi_threshold)
    cloud_limit = int(max_cloud_pct)
    period_start, period_end = indices.month_bounds(month)

    region = ee.Geometry(geometry, None, False)

    # One projected CRS for the entire reduction, derived from the AOI footprint (see _utm_crs).
    # Every reduction below uses this same CRS, so the mean/median and both area sums are taken
    # on one grid rather than being resampled into different projections.
    lon, lat = _representative_point(geometry)
    crs = _utm_crs(lon, lat)

    try:
        collection = (
            ee.ImageCollection(settings.SATELLITE_COLLECTION)
            .filterBounds(region)
            .filterDate(period_start, period_end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_limit))
        )
        scene_count = int(collection.size().getInfo() or 0)
    except GeeError:
        raise
    except Exception as error:  # noqa: BLE001
        raise GeeQueryError(
            f"Earth Engine rejected the Sentinel-2 scene query for {month}: {type(error).__name__}.",
        ) from error

    base = {
        "month": month,
        "period_start": period_start,
        "period_end": period_end,
        "ndwi_threshold": threshold,
        "max_cloud_pct": cloud_limit,
        "collection": settings.SATELLITE_COLLECTION,
        "resolution_m": indices.NATIVE_PIXEL_SIZE_M,
        "projection": crs,
    }

    if scene_count == 0:
        return {**base, "sensor": None, **indices.summarize(None, threshold=threshold, scene_count=0)}

    excluded = list(indices.SCL_EXCLUDED_CLASSES)

    def _masked_ndwi(image: Any) -> Any:
        scene_classification = image.select("SCL")
        valid = ee.Image(1)
        for excluded_class in excluded:
            valid = valid.And(scene_classification.neq(excluded_class))
        difference = image.normalizedDifference([indices.GREEN_BAND, indices.NIR_BAND]).rename("NDWI")
        return difference.updateMask(valid).copyProperties(image, ["system:time_start"])

    try:
        pixel_area_image = ee.Image.pixelArea()
        composite = collection.map(_masked_ndwi).median()

        ndwi_mean = _reduce_value(composite, ee.Reducer.mean(), region, target_crs=crs)
        ndwi_median = _reduce_value(composite, ee.Reducer.median(), region, target_crs=crs)
        valid_pixel_count = _reduce_value(composite.mask().gt(0), ee.Reducer.sum(), region, target_crs=crs)
        water_area_m2 = _reduce_value(
            composite.gte(threshold).multiply(pixel_area_image), ee.Reducer.sum(), region, target_crs=crs
        )
        valid_area_m2 = _reduce_value(
            composite.mask().gt(0).multiply(pixel_area_image), ee.Reducer.sum(), region, target_crs=crs
        )

        sensor_names: List[str] = []
        try:
            names = collection.aggregate_array("SPACECRAFT_NAME").getInfo() or []
            sensor_names = sorted({str(name) for name in names if name})
        except Exception:  # noqa: BLE001 - sensor label is nice-to-have, never fatal
            sensor_names = []
    except GeeError:
        raise
    except Exception as error:  # noqa: BLE001
        raise GeeQueryError(
            f"Earth Engine failed while reducing Sentinel-2 imagery for {month}: "
            f"{type(error).__name__}."
        ) from error

    summary = indices.summarize_metrics(
        ndwi_mean=ndwi_mean,
        ndwi_median=ndwi_median,
        water_area_m2=water_area_m2,
        valid_area_m2=valid_area_m2,
        valid_pixel_count=None if valid_pixel_count is None else int(valid_pixel_count),
        scene_count=scene_count,
    )

    return {
        **base,
        "sensor": "/".join(sensor_names) if sensor_names else "S2A/S2B/S2C",
        **summary,
    }
