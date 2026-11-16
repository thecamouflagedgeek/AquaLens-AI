"""Sentinel-2 spectral logic: SCL masking, NDWI, monthly aggregation.

Two implementations share one specification:

1. ``gee.monthly_ndwi`` performs these operations server-side in Earth Engine and is
   what production data comes from.
2. This module is the **reference implementation** over NumPy arrays. It documents
   the exact arithmetic, validates that the Earth Engine path matches, and is what
   automated tests exercise without any Google credentials.

Scientific position (do not overstate):

- NDWI is a *spectral indicator of surface water presence*, not a measurement of
  dissolved oxygen, BOD, turbidity, TSS, chlorophyll or chemical contamination.
- Water area from an NDWI threshold is an **estimate** derived from pixel counting at
  a stated pixel size. It is not ground truth and not a bathymetric area.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
GREEN_BAND = "B3"
NIR_BAND = "B8"
NATIVE_PIXEL_SIZE_M = 10.0          # both B3 and B8 are 10 m in S2_SR_HARMONIZED
NATIVE_PIXEL_AREA_M2 = NATIVE_PIXEL_SIZE_M ** 2
# Reductions run on a locally-derived projected CRS (see ``gee._utm_crs``), never on EPSG:4326.
# With ``scale=10`` in WGS84 the pixel is 10 degrees-units wide, so its ground size grows as
# 1/cos(latitude) and ``ee.Image.pixelArea()`` summed over that grid is not square metres either.
# A UTM zone (or polar stereographic near the poles) puts ``scale`` in metres, keeps every reduction
# on one grid, and makes the pixel-area sum a true square-metre measurement.
REFLECTANCE_SCALE = 0.0001          # S2 L2A DN scale; NDWI is scale-invariant
NDWI_THRESHOLD_DEFAULT = 0.0
MAX_CLOUD_PCT_DEFAULT = 60

ALGORITHM = "s2-sr-ndwi-monthly"
ALGORITHM_VERSION = "1.0.0"

# Sentinel-2 L2A Scene Classification Layer classes that are unusable for an
# optical water index. 0 = no data, 1 = saturated/defective, 3 = cloud shadow,
# 8 = cloud medium probability, 9 = cloud high probability, 10 = thin cirrus,
# 11 = snow/ice. Class 6 (water) is intentionally NOT used as a water mask:
# NDWI is thresholded, and SCL water is a separate product we do not want to
# conflate with the index under test.
SCL_EXCLUDED_CLASSES: Tuple[int, ...] = (0, 1, 3, 8, 9, 10, 11)

STATUS_OK = "ok"
STATUS_NO_SCENES = "no_scenes"
STATUS_NO_VALID_PIXELS = "no_valid_pixels"
STATUS_BELOW_MIN_PIXELS = "insufficient_pixels"

MIN_VALID_PIXELS = 25  # one 5x5 block at 10 m is the smallest defensible sample


def scl_valid_mask(scl: np.ndarray) -> np.ndarray:
    """Boolean mask of pixels whose SCL class is usable for NDWI."""
    classes = np.asarray(scl)
    valid = np.ones(classes.shape, dtype=bool)
    for excluded in SCL_EXCLUDED_CLASSES:
        valid &= classes != excluded
    return valid


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """NDWI = (Green - NIR) / (Green + NIR), with non-finite results set to NaN."""
    green_arr = np.asarray(green, dtype=np.float64)
    nir_arr = np.asarray(nir, dtype=np.float64)
    if green_arr.shape != nir_arr.shape:
        raise ValueError("Green and NIR arrays must share a shape.")

    denominator = green_arr + nir_arr
    result = np.full(green_arr.shape, np.nan, dtype=np.float64)
    usable = np.abs(denominator) > 1e-9
    result[usable] = (green_arr[usable] - nir_arr[usable]) / denominator[usable]
    return result


def scene_ndwi(green_dn: np.ndarray, nir_dn: np.ndarray, scl: Optional[np.ndarray] = None) -> np.ndarray:
    """Scale to reflectance, compute NDWI, then mask clouds/shadow via SCL."""
    green = np.asarray(green_dn, dtype=np.float64) * REFLECTANCE_SCALE
    nir = np.asarray(nir_dn, dtype=np.float64) * REFLECTANCE_SCALE
    values = ndwi(green, nir)
    if scl is not None:
        values = np.where(scl_valid_mask(scl), values, np.nan)
    return values


def monthly_composite(scenes: Sequence[np.ndarray]) -> Optional[np.ndarray]:
    """Per-pixel median of valid NDWI values across the month's scenes.

    NaN (masked or absent) is ignored per pixel, which is what Earth Engine's
    ``ImageCollection.median()`` does after ``updateMask``. Returns ``None`` when no
    usable scene exists, so callers cannot mistake an empty month for zero water.
    """
    stack = [np.asarray(scene, dtype=np.float64) for scene in scenes if scene is not None]
    if not stack:
        return None
    stacked = np.stack(stack, axis=0)
    if np.all(np.isnan(stacked)):
        return None
    # A pixel that is masked in every scene yields an all-NaN column; that is expected
    # and is reported through the summary status, not as a warning per pixel.
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        composite = np.nanmedian(stacked, axis=0)
    return np.where(np.isfinite(composite), composite, np.nan)


def summarize(
    composite: Optional[np.ndarray],
    *,
    threshold: float,
    scene_count: int,
    pixel_area_m2: float = NATIVE_PIXEL_AREA_M2,
    min_valid_pixels: int = MIN_VALID_PIXELS,
) -> Dict[str, Any]:
    """Turn a monthly NDWI composite into a persistable monthly record.

    Status, fraction and rounding decisions live in :func:`summarize_metrics`, so there is
    exactly one place that defines "no usable imagery". A month without usable imagery
    yields ``no_scenes``/``no_valid_pixels`` and null measurements — never 0.0 water area.
    """
    empty = dict(
        ndwi_mean=None,
        ndwi_median=None,
        water_area_m2=None,
        valid_area_m2=None,
        valid_pixel_count=0,
        scene_count=scene_count,
        min_valid_pixels=min_valid_pixels,
    )
    if composite is None:
        return summarize_metrics(**empty)

    values = np.asarray(composite, dtype=np.float64)
    finite = np.isfinite(values)
    valid_pixels = int(np.count_nonzero(finite))
    if valid_pixels == 0:
        return summarize_metrics(**empty)

    usable = values[finite]
    water_pixels = int(np.count_nonzero(usable >= float(threshold)))
    return summarize_metrics(
        ndwi_mean=float(np.mean(usable)),
        ndwi_median=float(np.median(usable)),
        water_area_m2=water_pixels * float(pixel_area_m2),
        valid_area_m2=valid_pixels * float(pixel_area_m2),
        valid_pixel_count=valid_pixels,
        scene_count=scene_count,
        min_valid_pixels=min_valid_pixels,
    )


def summarize_metrics(
    *,
    ndwi_mean: Optional[float],
    ndwi_median: Optional[float],
    water_area_m2: Optional[float],
    valid_area_m2: Optional[float],
    valid_pixel_count: Optional[int],
    scene_count: int,
    min_valid_pixels: int = MIN_VALID_PIXELS,
) -> Dict[str, Any]:
    """Assemble a monthly record from Earth-Engine reduced (not array) quantities.

    Used by the Earth Engine path so both implementations agree on status semantics:
    an empty or unusable month is reported, never converted into a zero measurement.
    """
    if scene_count <= 0:
        return {
            "status": STATUS_NO_SCENES,
            "ndwi_mean": None,
            "ndwi_median": None,
            "water_area_km2": None,
            "water_fraction": None,
            "valid_pixel_count": 0,
            "scene_count": 0,
        }

    pixels = int(valid_pixel_count or 0)
    if ndwi_mean is None or pixels == 0:
        return {
            "status": STATUS_NO_VALID_PIXELS,
            "ndwi_mean": None,
            "ndwi_median": None,
            "water_area_km2": None,
            "water_fraction": None,
            "valid_pixel_count": 0,
            "scene_count": int(scene_count),
        }

    area_km2 = None if water_area_m2 is None else round(float(water_area_m2) / 1_000_000.0, 6)
    fraction = None
    if water_area_m2 is not None and valid_area_m2 not in (None, 0):
        fraction = round(float(water_area_m2) / float(valid_area_m2), 6)

    return {
        "status": STATUS_OK if pixels >= min_valid_pixels else STATUS_BELOW_MIN_PIXELS,
        "ndwi_mean": round(float(ndwi_mean), 6),
        "ndwi_median": None if ndwi_median is None else round(float(ndwi_median), 6),
        "water_area_km2": area_km2,
        "water_fraction": fraction,
        "valid_pixel_count": pixels,
        "scene_count": int(scene_count),
    }


def describe_method() -> Dict[str, Any]:
    """Algorithm provenance stored alongside every observation."""
    return {
        "algorithm": ALGORITHM,
        "algorithm_version": ALGORITHM_VERSION,
        "collection": COLLECTION,
        "bands": {"green": GREEN_BAND, "nir": NIR_BAND},
        "pixel_size_m": NATIVE_PIXEL_SIZE_M,
        "projection_strategy": (
            "one locally-derived projected CRS per AOI (UTM zone, or polar stereographic near the "
            "poles); never a geographic CRS with a metre scale"
        ),
        "cloud_mask": {
            "source": "SCL",
            "excluded_classes": list(SCL_EXCLUDED_CLASSES),
            "method": "per-pixel exclusion of cloud, cloud shadow, cirrus, snow and no-data classes",
        },
        "aggregation": "per-pixel median NDWI of valid scenes within the calendar month",
        "water_area": "count of pixels with NDWI >= threshold multiplied by 100 m2 (10 m pixel), expressed in km2",
        "caveats": [
            "NDWI is a spectral indicator of surface water, not a water-quality measurement.",
            "NDWI-threshold water area is an estimate, not surveyed or bathymetric ground truth.",
            "Monthly median compositing can under-represent short flood or drawdown events.",
        ],
    }


def month_bounds(month: str) -> Tuple[str, str]:
    """Return inclusive start and exclusive end ISO dates for a 'YYYY-MM' month."""
    year, month_number = _parse_month(month)
    start = (year, month_number, 1)
    if month_number == 12:
        end = (year + 1, 1, 1)
    else:
        end = (year, month_number + 1, 1)
    return _iso(start), _iso(end)


def _iso(parts: Tuple[int, int, int]) -> str:
    return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"


def _parse_month(month: str) -> Tuple[int, int]:
    text = str(month)
    try:
        year_text, month_text = text.split("-")
        year, month_number = int(year_text), int(month_text)
    except (ValueError, AttributeError) as error:
        raise ValueError(f"Month must use the YYYY-MM format, got {month!r}.") from error
    if not 1 <= month_number <= 12:
        raise ValueError(f"Month number out of range in {month!r}.")
    if not 1970 <= year <= 2100:
        raise ValueError(f"Year out of range in {month!r}.")
    return year, month_number


def month_sequence(start_month: str, end_month: str) -> List[str]:
    """Inclusive list of 'YYYY-MM' months between two months."""
    start_year, start_number = _parse_month(start_month)
    end_year, end_number = _parse_month(end_month)
    if (start_year, start_number) > (end_year, end_number):
        raise ValueError("Start month must be on or before the end month.")

    months: List[str] = []
    year, number = start_year, start_number
    while (year, number) <= (end_year, end_number):
        months.append(f"{year:04d}-{number:02d}")
        number += 1
        if number == 13:
            year, number = year + 1, 1
    return months


def shift_months(month: str, delta: int) -> str:
    """Shift a 'YYYY-MM' month by a signed number of months."""
    year, number = _parse_month(month)
    total = year * 12 + (number - 1) + int(delta)
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def default_window(months: int = 24, today: Optional[str] = None) -> Tuple[str, str]:
    """Default historical window: the last ``months`` complete months."""
    from datetime import date

    reference = date.today() if today is None else date.fromisoformat(today)
    current = f"{reference.year:04d}-{reference.month:02d}"
    end = shift_months(current, -1)          # most recently complete month
    start = shift_months(end, -(max(1, int(months)) - 1))
    return start, end
