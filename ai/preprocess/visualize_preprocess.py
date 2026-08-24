"""
AquaLens AI - Objective 1
Advanced Preprocessing Visualization

Visualizes:
1. Original image
2. Resized image
3. Denoised image
4. CLAHE-normalized image
5. Grayscale representation
6. HSV representation
7. LAB representation
8. RGB channel distributions
9. HSV channel distributions
10. LAB channel distributions
11. Grayscale histogram
12. Edge map
13. Intensity statistics

Purpose:
    Validate that preprocessing preserves meaningful visual
    information before feature extraction.

The original UIEB dataset is NEVER modified.
"""

from pathlib import Path

import cv2
import numpy as np
import matplotlib.pyplot as plt

from ai.preprocess.image_preprocess import (
    ImagePreprocessor,
    PreprocessingConfig,
)


# ============================================================
# PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

IMAGE_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "UIEB"
    / "raw-890"
    / "2_img_.png"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "results"
    / "O1"
    / "preprocessing_visualization"
)

OUTPUT_PATH = (
    OUTPUT_DIR
    / "advanced_preprocessing_analysis.png"
)


# ============================================================
# IMAGE CONVERSION UTILITIES
# ============================================================

def bgr_to_rgb(image):
    """Convert BGR image to RGB."""

    return cv2.cvtColor(
        image,
        cv2.COLOR_BGR2RGB
    )


def hsv_to_rgb(hsv):
    """Convert HSV representation to RGB for visualization."""

    return cv2.cvtColor(
        hsv,
        cv2.COLOR_HSV2RGB
    )


def lab_to_rgb(lab):
    """Convert LAB representation to RGB for visualization."""

    return cv2.cvtColor(
        lab,
        cv2.COLOR_LAB2RGB
    )


# ============================================================
# EDGE DETECTION
# ============================================================

def generate_edge_map(grayscale):
    """
    Generate Canny edge map.

    This is NOT part of the final feature extraction yet.
    It is used here to visually inspect whether preprocessing
    preserves structural information.
    """

    edges = cv2.Canny(
        grayscale,
        threshold1=50,
        threshold2=150
    )

    return edges


# ============================================================
# STATISTICS
# ============================================================

def calculate_statistics(image_rgb):
    """
    Calculate basic RGB statistics.
    """

    statistics = {}

    channels = {
        "Red": image_rgb[:, :, 0],
        "Green": image_rgb[:, :, 1],
        "Blue": image_rgb[:, :, 2],
    }

    for name, channel in channels.items():

        statistics[name] = {
            "mean": float(np.mean(channel)),
            "std": float(np.std(channel)),
            "min": int(np.min(channel)),
            "max": int(np.max(channel)),
        }

    return statistics


# ============================================================
# MAIN VISUALIZATION
# ============================================================

def visualize_preprocessing():

    # --------------------------------------------------------
    # Validate image path
    # --------------------------------------------------------

    if not IMAGE_PATH.exists():

        raise FileNotFoundError(
            f"\nImage not found:\n{IMAGE_PATH}\n\n"
            "Update IMAGE_PATH with an actual UIEB image."
        )

    print("\n")
    print("=" * 70)
    print("        AquaLens AI - Advanced O1 Visualization")
    print("=" * 70)

    print(
        f"Input image:\n{IMAGE_PATH}"
    )

    # --------------------------------------------------------
    # Configure preprocessing
    # --------------------------------------------------------

    config = PreprocessingConfig(

        width=256,
        height=256,

        denoise_enabled=True,
        denoise_method="gaussian",

        normalization_enabled=True,
        normalization_method="clahe",

        gaussian_kernel_size=5,
        gaussian_sigma=0,

        clahe_clip_limit=2.0,
        clahe_grid_size=(8, 8),
    )

    preprocessor = ImagePreprocessor(
        config=config
    )

    # --------------------------------------------------------
    # Load + process
    # --------------------------------------------------------

    original_bgr = preprocessor.load_image(
        str(IMAGE_PATH)
    )

    result = preprocessor.process(
        original_bgr
    )

    # --------------------------------------------------------
    # Convert representations
    # --------------------------------------------------------

    original_rgb = bgr_to_rgb(
        result.original
    )

    resized_rgb = result.resized

    denoised_rgb = result.denoised

    normalized_rgb = result.normalized

    grayscale = result.grayscale

    hsv = result.hsv

    lab = result.lab

    hsv_rgb = hsv_to_rgb(
        hsv
    )

    lab_rgb = lab_to_rgb(
        lab
    )

    # --------------------------------------------------------
    # Edge map
    # --------------------------------------------------------

    edges = generate_edge_map(
        grayscale
    )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    original_stats = calculate_statistics(
        original_rgb
    )

    normalized_stats = calculate_statistics(
        normalized_rgb
    )

    # ========================================================
    # FIGURE 1
    # IMAGE PROCESSING PIPELINE
    # ========================================================

    fig1, axes = plt.subplots(
        2,
        4,
        figsize=(18, 9)
    )

    fig1.suptitle(
        "AquaLens AI — O1 Image Preprocessing Pipeline",
        fontsize=20,
        fontweight="bold"
    )

    images = [
        original_rgb,
        resized_rgb,
        denoised_rgb,
        normalized_rgb,
        grayscale,
        hsv_rgb,
        lab_rgb,
        edges,
    ]

    titles = [
        "1. Original",
        "2. Resized — 256×256",
        "3. Gaussian Denoised",
        "4. CLAHE Normalized",
        "5. Grayscale",
        "6. HSV Representation",
        "7. LAB Representation",
        "8. Edge Structure",
    ]

    for ax, image, title in zip(
        axes.flat,
        images,
        titles
    ):

        if title == "5. Grayscale":
            ax.imshow(
                image,
                cmap="gray"
            )

        elif title == "8. Edge Structure":
            ax.imshow(
                image,
                cmap="gray"
            )

        else:
            ax.imshow(
                image
            )

        ax.set_title(
            title,
            fontsize=12,
            fontweight="bold"
        )

        ax.axis("off")

    plt.tight_layout(
        rect=[0, 0, 1, 0.94]
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    pipeline_path = (
        OUTPUT_DIR
        / "01_pipeline_comparison.png"
    )

    fig1.savefig(
        pipeline_path,
        dpi=300,
        bbox_inches="tight"
    )

    # ========================================================
    # FIGURE 2
    # RGB HISTOGRAM ANALYSIS
    # ========================================================

    fig2, ax = plt.subplots(
        figsize=(12, 7)
    )

    channel_names = [
        "Red",
        "Green",
        "Blue",
    ]

    channel_indices = [
        0,
        1,
        2,
    ]

    for name, index in zip(
        channel_names,
        channel_indices
    ):

        histogram = cv2.calcHist(
            [normalized_rgb],
            [index],
            None,
            [256],
            [0, 256]
        )

        ax.plot(
            histogram,
            label=name,
            linewidth=2
        )

    ax.set_title(
        "Normalized Image — RGB Intensity Distribution",
        fontsize=16,
        fontweight="bold"
    )

    ax.set_xlabel(
        "Pixel Intensity"
    )

    ax.set_ylabel(
        "Pixel Frequency"
    )

    ax.legend()

    ax.grid(
        alpha=0.25
    )

    plt.tight_layout()

    histogram_path = (
        OUTPUT_DIR
        / "02_rgb_histogram.png"
    )

    fig2.savefig(
        histogram_path,
        dpi=300,
        bbox_inches="tight"
    )

    # ========================================================
    # FIGURE 3
    # HSV HISTOGRAM ANALYSIS
    # ========================================================

    fig3, axes_hsv = plt.subplots(
        1,
        3,
        figsize=(16, 5)
    )

    hsv_names = [
        "Hue",
        "Saturation",
        "Value",
    ]

    for index, name in enumerate(
        hsv_names
    ):

        axes_hsv[index].hist(
            hsv[:, :, index].ravel(),
            bins=50
        )

        axes_hsv[index].set_title(
            f"{name} Distribution",
            fontweight="bold"
        )

        axes_hsv[index].set_xlabel(
            name
        )

        axes_hsv[index].set_ylabel(
            "Frequency"
        )

        axes_hsv[index].grid(
            alpha=0.25
        )

    fig3.suptitle(
        "HSV Feature Distribution",
        fontsize=18,
        fontweight="bold"
    )

    plt.tight_layout()

    hsv_path = (
        OUTPUT_DIR
        / "03_hsv_distribution.png"
    )

    fig3.savefig(
        hsv_path,
        dpi=300,
        bbox_inches="tight"
    )

    # ========================================================
    # FIGURE 4
    # LAB HISTOGRAM ANALYSIS
    # ========================================================

    fig4, axes_lab = plt.subplots(
        1,
        3,
        figsize=(16, 5)
    )

    lab_names = [
        "L* — Lightness",
        "a* — Green ↔ Red",
        "b* — Blue ↔ Yellow",
    ]

    for index, name in enumerate(
        lab_names
    ):

        axes_lab[index].hist(
            lab[:, :, index].ravel(),
            bins=50
        )

        axes_lab[index].set_title(
            name,
            fontweight="bold"
        )

        axes_lab[index].set_xlabel(
            "Value"
        )

        axes_lab[index].set_ylabel(
            "Frequency"
        )

        axes_lab[index].grid(
            alpha=0.25
        )

    fig4.suptitle(
        "LAB Feature Distribution",
        fontsize=18,
        fontweight="bold"
    )

    plt.tight_layout()

    lab_path = (
        OUTPUT_DIR
        / "04_lab_distribution.png"
    )

    fig4.savefig(
        lab_path,
        dpi=300,
        bbox_inches="tight"
    )

    # ========================================================
    # FIGURE 5
    # ORIGINAL VS NORMALIZED STATISTICS
    # ========================================================

    fig5, axes_stats = plt.subplots(
        1,
        2,
        figsize=(14, 6)
    )

    names = [
        "Red",
        "Green",
        "Blue",
    ]

    original_means = [
        original_stats[name]["mean"]
        for name in names
    ]

    normalized_means = [
        normalized_stats[name]["mean"]
        for name in names
    ]

    # Mean comparison

    x = np.arange(
        len(names)
    )

    width = 0.35

    axes_stats[0].bar(
        x - width / 2,
        original_means,
        width,
        label="Original"
    )

    axes_stats[0].bar(
        x + width / 2,
        normalized_means,
        width,
        label="Normalized"
    )

    axes_stats[0].set_xticks(
        x
    )

    axes_stats[0].set_xticklabels(
        names
    )

    axes_stats[0].set_ylabel(
        "Mean Intensity"
    )

    axes_stats[0].set_title(
        "Mean RGB Intensity",
        fontweight="bold"
    )

    axes_stats[0].legend()

    axes_stats[0].grid(
        axis="y",
        alpha=0.25
    )

    # Standard deviation comparison

    original_std = [
        original_stats[name]["std"]
        for name in names
    ]

    normalized_std = [
        normalized_stats[name]["std"]
        for name in names
    ]

    axes_stats[1].bar(
        x - width / 2,
        original_std,
        width,
        label="Original"
    )

    axes_stats[1].bar(
        x + width / 2,
        normalized_std,
        width,
        label="Normalized"
    )

    axes_stats[1].set_xticks(
        x
    )

    axes_stats[1].set_xticklabels(
        names
    )

    axes_stats[1].set_ylabel(
        "Standard Deviation"
    )

    axes_stats[1].set_title(
        "RGB Variation",
        fontweight="bold"
    )

    axes_stats[1].legend()

    axes_stats[1].grid(
        axis="y",
        alpha=0.25
    )

    fig5.suptitle(
        "Preprocessing Statistical Comparison",
        fontsize=18,
        fontweight="bold"
    )

    plt.tight_layout()

    statistics_path = (
        OUTPUT_DIR
        / "05_preprocessing_statistics.png"
    )

    fig5.savefig(
        statistics_path,
        dpi=300,
        bbox_inches="tight"
    )

    # ========================================================
    # CONSOLE REPORT
    # ========================================================

    print("\n")
    print("=" * 70)
    print("              PREPROCESSING ANALYSIS")
    print("=" * 70)

    print(
        f"\nOriginal resolution:"
        f" {original_rgb.shape[1]} × "
        f"{original_rgb.shape[0]}"
    )

    print(
        "\nProcessed resolution:"
        f" {normalized_rgb.shape[1]} × "
        f"{normalized_rgb.shape[0]}"
    )

    print("\nOriginal RGB statistics:")

    for channel in names:

        print(
            f"  {channel:<6} "
            f"Mean = "
            f"{original_stats[channel]['mean']:.2f} | "
            f"Std = "
            f"{original_stats[channel]['std']:.2f}"
        )

    print("\nNormalized RGB statistics:")

    for channel in names:

        print(
            f"  {channel:<6} "
            f"Mean = "
            f"{normalized_stats[channel]['mean']:.2f} | "
            f"Std = "
            f"{normalized_stats[channel]['std']:.2f}"
        )

    print("\nGenerated visualizations:")

    print(
        f"  ✓ {pipeline_path}"
    )

    print(
        f"  ✓ {histogram_path}"
    )

    print(
        f"  ✓ {hsv_path}"
    )

    print(
        f"  ✓ {lab_path}"
    )

    print(
        f"  ✓ {statistics_path}"
    )

    print("\n")
    print("=" * 70)
    print("          Visualization completed successfully")
    print("=" * 70)

    # --------------------------------------------------------
    # Display all figures
    # --------------------------------------------------------

    plt.show()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    visualize_preprocessing()