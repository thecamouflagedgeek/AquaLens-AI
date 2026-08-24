from pathlib import Path
from collections import Counter
import logging
import json
import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR=PROJECT_ROOT / "data" / "raw" / "UIEB" / "raw-890"
RESULTS_DIR = PROJECT_ROOT / "results" / "O1"
REPORT_PATH = RESULTS_DIR / "dataset_validation.json"
SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s",)
logger = logging.getLogger("Aqualens - Data Validaton")

def validate(image_path: Path) -> dict:
    result = {
        "filename":image_path.name,
        "path":str(image_path),
        "extension":image_path.suffix.lower(),
        "readable": False,
        "width": None,
        "height": None,
        "channels": None,
        "dtype": None,
        "error": None,
    }

    try:
        image = cv2.imread(str(image_path),cv2.IMREAD_UNCHANGED)

        if image is None:
            result["error"] = "OpenCV could not read image"
            return result
        result["readable"] = True
        result["height"] = image.shape[0]
        result["width"] = image.shape[1]
        result["dtype"] = str(image.dtype)

        if image.ndim == 2:
            result["channels"] = 1
        elif image.ndim == 3:
            result["channels"] = image.shape[2]
        else:
            result["channels"] = None

    except Exception as e:
        result["error"] = str(exc)

    return result

def find_images(dataset_dir: Path) -> list[Path]:
    """
    Find supported image files recursively.
    """

    if not dataset_dir.exists():
        raise FileNotFoundError(
            f"Dataset directory does not exist:\n{dataset_dir}"
        )

    image_files = [
        path
        for path in dataset_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    return sorted(image_files)


def validate_dataset(dataset_dir: Path) -> dict:

    logger.info("UIEB dataset validation...")
    logger.info(f"Dataset: {dataset_dir}")

    image_files = find_images(dataset_dir)

    if not image_files:
        raise RuntimeError(
            f"No supported images found in:\n{dataset_dir}"
        )

    logger.info(f"Found {len(image_files)} image files.")

    results = []

    for index, image_path in enumerate(image_files, start=1):

        result = validate(image_path)
        results.append(result)

        if index % 100 == 0 or index == len(image_files):
            logger.info(
                f"Validated {index}/{len(image_files)} images"
            )

    readable_images = [
        result for result in results
        if result["readable"]
    ]

    unreadable_images = [
        result for result in results
        if not result["readable"]
    ]

    extensions = Counter(
        result["extension"]
        for result in results
    )

    channel_distribution = Counter(
        result["channels"]
        for result in readable_images
    )

    resolution_distribution = Counter(
        (
            result["width"],
            result["height"]
        )
        for result in readable_images
    )

    width_values = [
        result["width"]
        for result in readable_images
    ]

    height_values = [
        result["height"]
        for result in readable_images
    ]

    filenames = [
        result["filename"]
        for result in results
    ]

    filename_counts = Counter(filenames)

    duplicate_filenames = {
        filename: count
        for filename, count in filename_counts.items()
        if count > 1
    }

    report = {
        "dataset": "UIEB",
        "dataset_path": str(dataset_dir),

        "summary": {
            "total_images": len(results),
            "readable_images": len(readable_images),
            "unreadable_images": len(unreadable_images),
            "unique_filenames": len(filename_counts),
            "duplicate_filename_count": len(
                duplicate_filenames
            ),
        },

        "file_formats": dict(extensions),

        "channels": {
            str(channel): count
            for channel, count in channel_distribution.items()
        },

        "resolution": {
            "minimum_width": min(width_values),
            "maximum_width": max(width_values),
            "minimum_height": min(height_values),
            "maximum_height": max(height_values),
            "unique_resolutions": len(
                resolution_distribution
            ),
        },

        "duplicate_filenames": duplicate_filenames,

        "unreadable_images": [
            {
                "filename": result["filename"],
                "path": result["path"],
                "error": result["error"],
            }
            for result in unreadable_images
        ],
    }

    return report

def save_report(report: dict, output_path: Path) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with output_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            indent=4
        )

    logger.info(
        f"Validation report saved to: {output_path}"
    )


def print_summary(report: dict) -> None:

    summary = report["summary"]

    print("\n")
    print("=" * 60)
    print("           AquaLens AI - UIEB Validation")
    print("=" * 60)

    print(
        f"Total images       : "
        f"{summary['total_images']}"
    )

    print(
        f"Readable images    : "
        f"{summary['readable_images']}"
    )

    print(
        f"Unreadable images  : "
        f"{summary['unreadable_images']}"
    )

    print(
        f"Duplicate filenames: "
        f"{summary['duplicate_filename_count']}"
    )

    print("\nFile formats:")

    for extension, count in report["file_formats"].items():
        print(
            f"  {extension:<8} : {count}"
        )

    print("\nChannels:")

    for channel, count in report["channels"].items():
        print(
            f"  {channel} channel(s) : {count}"
        )

    resolution = report["resolution"]

    print("\nResolution range:")

    print(
        f"  Width  : "
        f"{resolution['minimum_width']} - "
        f"{resolution['maximum_width']}"
    )

    print(
        f"  Height : "
        f"{resolution['minimum_height']} - "
        f"{resolution['maximum_height']}"
    )

    print(
        f"  Unique resolutions : "
        f"{resolution['unique_resolutions']}"
    )

    print("=" * 60)

    if summary["unreadable_images"] == 0:
        print("STATUS: Dataset validation PASSED")
    else:
        print("STATUS: Dataset contains unreadable images")

    print("=" * 60)
    print()


def main() -> None:

    try:

        report = validate_dataset(
            DATASET_DIR
        )

        save_report(
            report,
            REPORT_PATH
        )

        print_summary(report)

    except Exception as exc:

        logger.error(
            f"Dataset validation failed: {exc}"
        )

        raise


if __name__ == "__main__":
    main()
