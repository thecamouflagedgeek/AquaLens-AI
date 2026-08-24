"""
AquaLens AI - Objective 1
Unified Feature Extraction Pipeline

Purpose:
    Combine colour, texture, and structural features
    extracted from a preprocessed water image.

Pipeline:

    Water Image
         |
         v
    Preprocessing
         |
         +------------------+
         |                  |
         v                  v
      Colour             Texture
         |                  |
         +--------+---------+
                  |
                  v
              Structure
                  |
                  v
          Unified Feature Vector

The resulting feature vector forms the numerical
representation used by later AquaLens stages.

IMPORTANT:
    This module performs feature extraction only.
    It does NOT perform contamination classification
    or anomaly detection.
"""

import os
import cv2
import numpy as np
import pandas as pd

from ai.feature.colour_features import (
    ColourFeatureExtractor
)

from ai.feature.texture import (
    TextureFeatureExtractor
)

from ai.feature.structure import (
    StructuralFeatureExtractor
)


class AquaLensFeatureExtractor:
    """
    Unified AquaLens feature extraction pipeline.

    Combines:

        1. Colour features
        2. Texture features
        3. Structural features
    """

    def __init__(self):

        self.colour_extractor = (
            ColourFeatureExtractor()
        )

        self.texture_extractor = (
            TextureFeatureExtractor()
        )

        self.structure_extractor = (
            StructuralFeatureExtractor()
        )

        self.feature_names = []

    # ========================================================
    # IMAGE LOADING
    # ========================================================

    @staticmethod
    def load_image(image_path):
        """
        Load an image from disk and convert BGR → RGB.

        Parameters
        ----------
        image_path : str
            Path to image.

        Returns
        -------
        np.ndarray
            RGB image.
        """

        if not os.path.exists(image_path):

            raise FileNotFoundError(
                f"Image not found:\n{image_path}"
            )

        image_bgr = cv2.imread(
            image_path
        )

        if image_bgr is None:

            raise ValueError(
                f"OpenCV could not read image:\n"
                f"{image_path}"
            )

        image_rgb = cv2.cvtColor(
            image_bgr,
            cv2.COLOR_BGR2RGB
        )

        return image_rgb

    # ========================================================
    # SINGLE IMAGE FEATURE EXTRACTION
    # ========================================================

    def extract_from_image(
        self,
        image_rgb,
        image_path=None
    ):
        """
        Extract the complete AquaLens feature vector
        from a single RGB image.

        Parameters
        ----------
        image_rgb : np.ndarray
            RGB image.

        image_path : str, optional
            Original image path.

        Returns
        -------
        dict
            Unified feature dictionary.
        """

        if image_rgb is None:

            raise ValueError(
                "Input image cannot be None."
            )

        # ----------------------------------------------------
        # Colour
        # ----------------------------------------------------

        colour_features = (
            self.colour_extractor.extract(
                image_rgb
            )
        )

        # ----------------------------------------------------
        # Texture
        # ----------------------------------------------------

        texture_features = (
            self.texture_extractor.extract(
                image_rgb
            )
        )

        # ----------------------------------------------------
        # Structure
        # ----------------------------------------------------

        structural_features = (
            self.structure_extractor.extract(
                image_rgb
            )
        )

        # ----------------------------------------------------
        # Combine
        # ----------------------------------------------------

        features = {}

        features.update(
            colour_features
        )

        features.update(
            texture_features
        )

        features.update(
            structural_features
        )

        # ----------------------------------------------------
        # Metadata
        # ----------------------------------------------------

        if image_path is not None:

            features[
                "image_name"
            ] = os.path.basename(
                image_path
            )

            features[
                "image_path"
            ] = image_path

        features[
            "image_height"
        ] = int(
            image_rgb.shape[0]
        )

        features[
            "image_width"
        ] = int(
            image_rgb.shape[1]
        )

        features[
            "image_channels"
        ] = int(
            image_rgb.shape[2]
        )

        self.feature_names = list(
            features.keys()
        )

        return features

    # ========================================================
    # SINGLE IMAGE FROM PATH
    # ========================================================

    def extract_from_path(
        self,
        image_path
    ):
        """
        Load an image and extract its complete
        AquaLens feature vector.
        """

        image_rgb = self.load_image(
            image_path
        )

        return self.extract_from_image(
            image_rgb,
            image_path=image_path
        )

    # ========================================================
    # BATCH EXTRACTION
    # ========================================================

    def extract_from_directory(
        self,
        directory,
        extensions=None
    ):
        """
        Extract features from all supported images
        inside a directory.

        Parameters
        ----------
        directory : str
            Root directory containing images.

        extensions : tuple, optional
            Supported image extensions.

        Returns
        -------
        pandas.DataFrame
            Feature matrix.
        """

        if extensions is None:

            extensions = (
                ".jpg",
                ".jpeg",
                ".png",
                ".bmp",
                ".tif",
                ".tiff"
            )

        if not os.path.isdir(directory):

            raise NotADirectoryError(
                f"Directory not found:\n"
                f"{directory}"
            )

        image_paths = []

        # ----------------------------------------------------
        # Recursively find images
        # ----------------------------------------------------

        for root, _, files in os.walk(
            directory
        ):

            for filename in files:

                if filename.lower().endswith(
                    extensions
                ):

                    image_paths.append(
                        os.path.join(
                            root,
                            filename
                        )
                    )

        image_paths.sort()

        if len(image_paths) == 0:

            raise FileNotFoundError(
                f"No supported images found in:\n"
                f"{directory}"
            )

        print(
            f"\nFound {len(image_paths)} images."
        )

        # ----------------------------------------------------
        # Extract features
        # ----------------------------------------------------

        all_features = []

        for index, image_path in enumerate(
            image_paths,
            start=1
        ):

            print(
                f"[{index}/{len(image_paths)}] "
                f"Processing: "
                f"{os.path.basename(image_path)}"
            )

            try:

                features = (
                    self.extract_from_path(
                        image_path
                    )
                )

                all_features.append(
                    features
                )

            except Exception as error:

                print(
                    f"  WARNING: Failed to process "
                    f"{image_path}"
                )

                print(
                    f"  Reason: {error}"
                )

        if len(all_features) == 0:

            raise RuntimeError(
                "Feature extraction failed "
                "for all images."
            )

        dataframe = pd.DataFrame(
            all_features
        )

        return dataframe

    # ========================================================
    # SAVE FEATURES
    # ========================================================

    @staticmethod
    def save_features(
        dataframe,
        output_path
    ):
        """
        Save extracted feature vectors as CSV.
        """

        output_directory = os.path.dirname(
            output_path
        )

        if output_directory:

            os.makedirs(
                output_directory,
                exist_ok=True
            )

        dataframe.to_csv(
            output_path,
            index=False
        )

        print(
            f"\nFeature vectors saved to:"
            f"\n{output_path}"
        )

    # ========================================================
    # FEATURE SUMMARY
    # ========================================================

    @staticmethod
    def print_summary(
        dataframe
    ):
        """
        Print a concise summary of the generated
        feature dataset.
        """

        metadata_columns = {
            "image_name",
            "image_path",
            "image_height",
            "image_width",
            "image_channels"
        }

        feature_columns = [
            column
            for column in dataframe.columns
            if column not in metadata_columns
        ]

        print("\n")
        print("=" * 70)
        print(
            "          AQUAlens FEATURE EXTRACTION SUMMARY"
        )
        print("=" * 70)

        print(
            f"Images processed       : "
            f"{len(dataframe)}"
        )

        print(
            f"Total columns          : "
            f"{len(dataframe.columns)}"
        )

        print(
            f"Actual visual features : "
            f"{len(feature_columns)}"
        )

        print(
            f"Metadata columns       : "
            f"{len(metadata_columns.intersection(dataframe.columns))}"
        )

        print("\nFeature groups:")

        colour_count = sum(
            column.startswith("rgb_")
            or column.startswith("hsv_")
            or column.startswith("lab_")
            or column.startswith("colour_")
            for column in feature_columns
        )

        texture_count = sum(
            column.startswith("glcm_")
            or column.startswith("texture_")
            or column.startswith("local_")
            for column in feature_columns
        )

        structure_count = len(
            feature_columns
        ) - colour_count - texture_count

        print(
            f"  Colour features    : "
            f"{colour_count}"
        )

        print(
            f"  Texture features   : "
            f"{texture_count}"
        )

        print(
            f"  Structural features: "
            f"{structure_count}"
        )

        print("=" * 70)

    # ========================================================
    # TEST
    # ========================================================


if __name__ == "__main__":

    print("=" * 70)
    print(
        "       AquaLens AI - Unified Feature Extraction"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Configuration
    # --------------------------------------------------------

    test_image = (
        "data/raw/UIEB/raw-890/2_img_.png"
    )

    output_file = (
        "results/O1/feature_vectors.csv"
    )

    # --------------------------------------------------------
    # Initialize
    # --------------------------------------------------------

    extractor = (
        AquaLensFeatureExtractor()
    )

    # --------------------------------------------------------
    # Process one image first
    # --------------------------------------------------------

    print(
        f"\nInput image:"
        f"\n{test_image}"
    )

    features = (
        extractor.extract_from_path(
            test_image
        )
    )

    # --------------------------------------------------------
    # Convert to DataFrame
    # --------------------------------------------------------

    dataframe = pd.DataFrame(
        [features]
    )

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print(
        "             FEATURE VECTOR"
    )
    print("=" * 70)

    for column, value in features.items():

        if isinstance(
            value,
            (float, np.floating)
        ):

            print(
                f"{column:<45}"
                f"{value:.6f}"
            )

        else:

            print(
                f"{column:<45}"
                f"{value}"
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    extractor.print_summary(
        dataframe
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    extractor.save_features(
        dataframe,
        output_file
    )

    print("\n")
    print("=" * 70)
    print(
        "       FEATURE EXTRACTION SUCCESSFUL!"
    )
    print("=" * 70)