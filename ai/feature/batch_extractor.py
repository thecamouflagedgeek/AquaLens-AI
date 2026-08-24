"""
AquaLens AI - Objective 1
Production-Grade Batch Feature Extraction

Purpose:
    Process the complete UIEB image dataset and generate
    a unified numerical feature representation for each image.

Features:
    - Recursive image discovery
    - Corrupted-image detection
    - Exception-safe processing
    - Progress reporting
    - Failure logging
    - Incremental CSV checkpoints
    - Resume support
    - Final feature matrix
    - Extraction statistics

Output:
    results/O1/feature_vectors.csv
    results/O1/extraction_failures.csv
    results/O1/extraction_report.txt

Architecture:

    UIEB Dataset
         |
         v
    Image Discovery
         |
         v
    Image Validation
         |
         v
    AquaLensFeatureExtractor
         |
         +--------------------+
         |                    |
         v                    v
      SUCCESS               FAILURE
         |                    |
         v                    v
    Feature CSV          Failure CSV
         |
         v
    Extraction Report
"""

import os
import csv
import time
from datetime import datetime

import cv2
import pandas as pd

from ai.feature.feature_extractor import (
    AquaLensFeatureExtractor
)


# ============================================================
# CONFIGURATION
# ============================================================

DATASET_DIR = (
    "data/raw/UIEB"
)

OUTPUT_DIR = (
    "results/O1"
)

FEATURE_OUTPUT = (
    os.path.join(
        OUTPUT_DIR,
        "feature_vectors.csv"
    )
)

FAILURE_OUTPUT = (
    os.path.join(
        OUTPUT_DIR,
        "extraction_failures.csv"
    )
)

REPORT_OUTPUT = (
    os.path.join(
        OUTPUT_DIR,
        "extraction_report.txt"
    )
)

CHECKPOINT_INTERVAL = 25

SUPPORTED_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff"
)


# ============================================================
# DATASET DISCOVERY
# ============================================================

def discover_images(
    dataset_directory
):
    """
    Recursively discover all supported image files.

    Returns:
        Sorted list of image paths.
    """

    image_paths = []

    print(
        "\nScanning dataset..."
    )

    for root, _, files in os.walk(
        dataset_directory
    ):

        for filename in files:

            if filename.lower().endswith(
                SUPPORTED_EXTENSIONS
            ):

                image_paths.append(
                    os.path.join(
                        root,
                        filename
                    )
                )

    image_paths.sort()

    return image_paths


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image(
    image_path
):
    """
    Verify that OpenCV can actually decode the image.

    Returns:
        True if valid.
        False otherwise.
    """

    try:

        image = cv2.imread(
            image_path,
            cv2.IMREAD_COLOR
        )

        if image is None:
            return False

        if image.size == 0:
            return False

        if len(image.shape) != 3:
            return False

        if image.shape[2] != 3:
            return False

        return True

    except Exception:

        return False


# ============================================================
# DIRECTORY SETUP
# ============================================================

def setup_output_directory():
    """
    Create output directory if it doesn't exist.
    """

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )


# ============================================================
# LOAD EXISTING CHECKPOINT
# ============================================================

def load_existing_features():
    """
    Load previously processed feature vectors.

    This allows the extraction process to resume after
    interruption.

    Returns:
        DataFrame
        Set of already processed image paths
    """

    if not os.path.exists(
        FEATURE_OUTPUT
    ):

        return (
            pd.DataFrame(),
            set()
        )

    try:

        dataframe = pd.read_csv(
            FEATURE_OUTPUT
        )

        if "image_path" not in dataframe.columns:

            print(
                "\nWARNING:"
                "\nExisting feature CSV does not contain "
                "'image_path'."
                "\nStarting a fresh extraction."
            )

            return (
                pd.DataFrame(),
                set()
            )

        processed_paths = set(
            dataframe[
                "image_path"
            ].astype(str)
        )

        return (
            dataframe,
            processed_paths
        )

    except Exception as error:

        print(
            "\nWARNING: Could not load existing "
            "checkpoint."
        )

        print(
            f"Reason: {error}"
        )

        return (
            pd.DataFrame(),
            set()
        )


# ============================================================
# SAVE FEATURE CHECKPOINT
# ============================================================

def save_feature_checkpoint(
    features
):
    """
    Save currently extracted features to CSV.

    Uses a temporary file and replaces the previous
    checkpoint only after successful writing.
    """

    if not features:
        return

    dataframe = pd.DataFrame(
        features
    )

    temporary_file = (
        FEATURE_OUTPUT +
        ".tmp"
    )

    dataframe.to_csv(
        temporary_file,
        index=False
    )

    os.replace(
        temporary_file,
        FEATURE_OUTPUT
    )


# ============================================================
# FAILURE LOGGING
# ============================================================

def save_failures(
    failures
):
    """
    Save failed image records.
    """

    if not failures:
        return

    dataframe = pd.DataFrame(
        failures
    )

    dataframe.to_csv(
        FAILURE_OUTPUT,
        index=False
    )


# ============================================================
# PROGRESS DISPLAY
# ============================================================

def print_progress(
    current,
    total,
    successful,
    failed,
    start_time
):
    """
    Display extraction progress.
    """

    elapsed = (
        time.time() -
        start_time
    )

    percentage = (
        current /
        total *
        100
    )

    if current > 0:

        average_time = (
            elapsed /
            current
        )

        remaining = (
            average_time *
            (total - current)
        )

    else:

        remaining = 0

    minutes_remaining = (
        remaining /
        60
    )

    print(
        f"\rProgress: "
        f"{current}/{total} "
        f"({percentage:6.2f}%) | "
        f"Success: {successful} | "
        f"Failed: {failed} | "
        f"ETA: {minutes_remaining:6.1f} min",
        end="",
        flush=True
    )


# ============================================================
# REPORT GENERATION
# ============================================================

def generate_report(
    total_discovered,
    successful,
    failed,
    skipped,
    elapsed_time,
    feature_count
):
    """
    Generate a human-readable extraction report.
    """

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    success_rate = (
        successful /
        total_discovered *
        100
        if total_discovered > 0
        else 0
    )

    failure_rate = (
        failed /
        total_discovered *
        100
        if total_discovered > 0
        else 0
    )

    report = f"""
============================================================
              AQUAlens AI - O1 EXTRACTION REPORT
============================================================

Timestamp:
{timestamp}

Dataset:
{DATASET_DIR}

------------------------------------------------------------
DATASET STATISTICS
------------------------------------------------------------

Images discovered       : {total_discovered}
Successfully processed  : {successful}
Failed                  : {failed}
Skipped / already done  : {skipped}

Success rate            : {success_rate:.2f}%
Failure rate            : {failure_rate:.2f}%

------------------------------------------------------------
FEATURE STATISTICS
------------------------------------------------------------

Visual features/image   : {feature_count}

Feature groups:
    Colour
    Texture
    Structural

------------------------------------------------------------
PROCESSING PERFORMANCE
------------------------------------------------------------

Total processing time   : {elapsed_time / 60:.2f} minutes

Average time/image      : {
        elapsed_time / successful
        if successful > 0
        else 0
    :.3f} seconds

------------------------------------------------------------
OUTPUTS
------------------------------------------------------------

Feature vectors:
{FEATURE_OUTPUT}

Failed images:
{FAILURE_OUTPUT}

------------------------------------------------------------
STATUS
------------------------------------------------------------

Objective 1 batch feature extraction completed.

============================================================
"""

    with open(
        REPORT_OUTPUT,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            report
        )

    print(
        f"\n\nReport saved to:"
        f"\n{REPORT_OUTPUT}"
    )


# ============================================================
# MAIN EXTRACTION PIPELINE
# ============================================================

def run_batch_extraction():

    print(
        "=" * 70
    )

    print(
        "       AquaLens AI - O1 BATCH FEATURE EXTRACTION"
    )

    print(
        "=" * 70
    )

    start_time = time.time()

    setup_output_directory()

    # --------------------------------------------------------
    # Dataset discovery
    # --------------------------------------------------------

    image_paths = discover_images(
        DATASET_DIR
    )

    total_images = len(
        image_paths
    )

    print(
        f"\nDataset:"
        f"\n{DATASET_DIR}"
    )

    print(
        f"\nImages discovered: "
        f"{total_images}"
    )

    if total_images == 0:

        raise RuntimeError(
            "No supported images were found."
        )

    # --------------------------------------------------------
    # Load checkpoint
    # --------------------------------------------------------

    existing_dataframe, processed_paths = (
        load_existing_features()
    )

    if processed_paths:

        print(
            f"\nExisting checkpoint detected."
        )

        print(
            f"Already processed: "
            f"{len(processed_paths)} images"
        )

        print(
            "Resume mode enabled."
        )

    # --------------------------------------------------------
    # Initialize extractor
    # --------------------------------------------------------

    extractor = (
        AquaLensFeatureExtractor()
    )

    # --------------------------------------------------------
    # Runtime storage
    # --------------------------------------------------------

    new_features = []

    failures = []

    successful = 0

    failed = 0

    skipped = 0

    # --------------------------------------------------------
    # Process images
    # --------------------------------------------------------

    print(
        "\nStarting extraction..."
    )

    print(
        "-" * 70
    )

    for index, image_path in enumerate(
        image_paths,
        start=1
    ):

        # ----------------------------------------------------
        # Resume support
        # ----------------------------------------------------

        normalized_path = os.path.normpath(
            image_path
        )

        if normalized_path in processed_paths:

            skipped += 1

            print_progress(
                index,
                total_images,
                successful,
                failed,
                start_time
            )

            continue

        # ----------------------------------------------------
        # Validate image
        # ----------------------------------------------------

        if not validate_image(
            image_path
        ):

            failed += 1

            failures.append({

                "image_path":
                    image_path,

                "error_type":
                    "invalid_or_corrupted_image",

                "error_message":
                    "OpenCV could not decode image",

                "timestamp":
                    datetime.now().isoformat()
            })

            print_progress(
                index,
                total_images,
                successful,
                failed,
                start_time
            )

            continue

        # ----------------------------------------------------
        # Extract features
        # ----------------------------------------------------

        try:

            features = (
                extractor.extract_from_path(
                    image_path
                )
            )

            # Normalize path representation
            features[
                "image_path"
            ] = normalized_path

            new_features.append(
                features
            )

            successful += 1

        except Exception as error:

            failed += 1

            failures.append({

                "image_path":
                    normalized_path,

                "error_type":
                    type(error).__name__,

                "error_message":
                    str(error),

                "timestamp":
                    datetime.now().isoformat()
            })

        # ----------------------------------------------------
        # Checkpoint
        # ----------------------------------------------------

        if (
            len(new_features)
            >= CHECKPOINT_INTERVAL
        ):

            checkpoint_dataframe = (
                pd.DataFrame(
                    new_features
                )
            )

            if not existing_dataframe.empty:

                combined_dataframe = pd.concat(
                    [
                        existing_dataframe,
                        checkpoint_dataframe
                    ],
                    ignore_index=True
                )

            else:

                combined_dataframe = (
                    checkpoint_dataframe
                )

            save_feature_checkpoint(
                combined_dataframe.to_dict(
                    orient="records"
                )

            )

            existing_dataframe = (
                combined_dataframe
            )

            for feature in new_features:

                processed_paths.add(
                    os.path.normpath(
                        feature[
                            "image_path"
                        ]
                    )
                )

            new_features.clear()

            save_failures(
                failures
            )

        # ----------------------------------------------------
        # Progress
        # ----------------------------------------------------

        print_progress(
            index,
            total_images,
            successful,
            failed,
            start_time
        )

    # --------------------------------------------------------
    # Final checkpoint
    # --------------------------------------------------------

    if new_features:

        final_dataframe = pd.DataFrame(
            new_features
        )

        if not existing_dataframe.empty:

            final_dataframe = pd.concat(
                [
                    existing_dataframe,
                    final_dataframe
                ],
                ignore_index=True
            )

        save_feature_checkpoint(
            final_dataframe.to_dict(
                orient="records"
            )
        )

        existing_dataframe = (
            final_dataframe
        )

    # --------------------------------------------------------
    # Save failures
    # --------------------------------------------------------

    save_failures(
        failures
    )

    # --------------------------------------------------------
    # Final statistics
    # --------------------------------------------------------

    elapsed_time = (
        time.time() -
        start_time
    )

    if os.path.exists(
        FEATURE_OUTPUT
    ):

        final_dataframe = pd.read_csv(
            FEATURE_OUTPUT
        )

        metadata_columns = {
            "image_name",
            "image_path",
            "image_height",
            "image_width",
            "image_channels"
        }

        feature_columns = [
            column
            for column in final_dataframe.columns
            if column not in metadata_columns
        ]

        feature_count = len(
            feature_columns
        )

    else:

        feature_count = 0

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    generate_report(
        total_discovered=total_images,
        successful=successful,
        failed=failed,
        skipped=skipped,
        elapsed_time=elapsed_time,
        feature_count=feature_count
    )

    # --------------------------------------------------------
    # Final console output
    # --------------------------------------------------------

    print(
        "\n"
    )

    print(
        "=" * 70
    )

    print(
        "              EXTRACTION COMPLETED"
    )

    print(
        "=" * 70
    )

    print(
        f"Total discovered : {total_images}"
    )

    print(
        f"Successful       : {successful}"
    )

    print(
        f"Failed           : {failed}"
    )

    print(
        f"Skipped          : {skipped}"
    )

    print(
        f"Features/image   : {feature_count}"
    )

    print(
        f"Time taken       : "
        f"{elapsed_time / 60:.2f} minutes"
    )

    print(
        "\nFeature matrix:"
    )

    print(
        FEATURE_OUTPUT
    )

    print(
        "\nFailure log:"
    )

    print(
        FAILURE_OUTPUT
    )

    print(
        "\nReport:"
    )

    print(
        REPORT_OUTPUT
    )

    print(
        "=" * 70
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        run_batch_extraction()

    except KeyboardInterrupt:

        print(
            "\n\nExtraction interrupted by user."
        )

        print(
            "Any completed checkpoint has been preserved."
        )

    except Exception as error:

        print(
            "\n\nFATAL ERROR:"
        )

        print(
            str(error)
        )

        print(
            "\nPreviously saved checkpoints remain intact."
        )