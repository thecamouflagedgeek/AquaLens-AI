"""
AquaLens AI - ML Feature Extractor
Extracts 20 visual features from water images conforming to the fixed 20-feature schema.
"""

import cv2
import numpy as np
from typing import Dict, Any, Tuple
from .feature_schema import FEATURE_NAMES

EPS = 1e-6


def safe_stat(arr, func, default=0.0) -> float:
    arr = np.asarray(arr)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float(default)
    val = func(arr)
    if not np.isfinite(val):
        return float(default)
    return float(val)


def preprocess_image(image_bgr: np.ndarray, target_size: Tuple[int, int] = (256, 256)) -> np.ndarray:
    """Standard resize and light gaussian smoothing for stable feature extraction."""
    if image_bgr is None or image_bgr.size == 0:
        raise ValueError("Invalid image provided for preprocessing.")
    resized = cv2.resize(image_bgr, target_size, interpolation=cv2.INTER_AREA)
    denoised = cv2.GaussianBlur(resized, (5, 5), 0)
    return denoised


def reconstruct_20_features(image_bgr: np.ndarray, apply_preproc: bool = True) -> Dict[str, float]:
    """
    Extracts the exact 20 visual features required by the Objective 2 Random Forest model.
    Enforces strict feature ordering, robust fallback for non-finite values, and input validation.
    """
    if image_bgr is None or not isinstance(image_bgr, np.ndarray) or image_bgr.size == 0:
        raise ValueError("Input image is invalid, corrupted, or None.")

    if len(image_bgr.shape) != 3 or image_bgr.shape[2] != 3:
        raise ValueError(f"Expected a 3-channel BGR image, got shape {image_bgr.shape if hasattr(image_bgr, 'shape') else 'unknown'}")

    # Standardize image dimensions for consistent area and texture statistics
    img = preprocess_image(image_bgr) if apply_preproc else image_bgr

    # ---------- Colour Spaces ----------
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)

    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)

    h = hsv[:, :, 0].astype(np.float32)
    s = hsv[:, :, 1].astype(np.float32)

    # OpenCV LAB: L in [0, 255], a/b in [0, 255]
    lab_l = lab[:, :, 0].astype(np.float32)
    lab_a = lab[:, :, 1].astype(np.float32)
    lab_b = lab[:, :, 2].astype(np.float32)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # ---------- Segmentation for contour/component descriptors ----------
    gray_u8 = np.clip(gray, 0, 255).astype(np.uint8)
    _, binary = cv2.threshold(gray_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = np.ones((3, 3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    # ---------- Contours ----------
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour_areas = np.array([cv2.contourArea(c) for c in contours], dtype=np.float32)

    if contour_areas.size == 0:
        largest_contour_area = 0.0
        contour_area_std = 0.0
    else:
        largest_contour_area = float(np.max(contour_areas))
        contour_area_std = float(np.std(contour_areas))

    # ---------- Connected Components ----------
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    component_areas = stats[1:, cv2.CC_STAT_AREA].astype(np.float32)

    if component_areas.size == 0:
        component_area_mean = 0.0
        component_area_std = 0.0
        component_count = 0.0
    else:
        component_areas = component_areas[component_areas >= 5]
        component_area_mean = float(np.mean(component_areas)) if component_areas.size > 0 else 0.0
        component_area_std = float(np.std(component_areas)) if component_areas.size > 0 else 0.0
        component_count = float(component_areas.size)

    features = {
        "lab_a_min": safe_stat(lab_a, np.min),
        "rgb_2_median": safe_stat(g, np.median),
        "colour_ratio_gb": safe_stat(g / (b + EPS), np.median),
        "rgb_3_median": safe_stat(b, np.median),
        "hsv_hue_median": safe_stat(h, np.median),
        "colour_ratio_rb": safe_stat(r / (b + EPS), np.median),
        "lab_a_std": safe_stat(lab_a, np.std),
        "hsv_saturation_max": safe_stat(s, np.max),
        "lab_b_median": safe_stat(lab_b, np.median),
        "hsv_saturation_median": safe_stat(s, np.median),
        "lab_lightness_max": safe_stat(lab_l, np.max),
        "colour_cast_blue_red": safe_stat(b - r, np.mean),
        "rgb_3_max": safe_stat(b, np.max),
        "lab_b_max": safe_stat(lab_b, np.max),
        "texture_intensity_variance": float(np.var(gray)),
        "largest_contour_area": largest_contour_area,
        "contour_area_std": contour_area_std,
        "component_area_mean": component_area_mean,
        "component_area_std": component_area_std,
        "component_count": component_count,
    }

    # Strict contract enforcement: exact 20 features in exact order
    ordered_features = {}
    for name in FEATURE_NAMES:
        val = float(features[name])
        ordered_features[name] = 0.0 if not np.isfinite(val) else val

    return ordered_features


def feature_dict_to_vector(features: Dict[str, float]) -> np.ndarray:
    """Converts a feature dict into a 1D NumPy array adhering strictly to FEATURE_NAMES."""
    return np.array([float(features[name]) for name in FEATURE_NAMES], dtype=np.float32)
