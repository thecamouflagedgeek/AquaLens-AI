"""
AquaLens AI - Objective 1
Colour Feature Extraction

Purpose:
    Extract quantitative colour characteristics from a
    preprocessed water image.

Colour spaces:
    - RGB
    - HSV
    - LAB

These features will later form part of the AquaLens
Water Feature Vector.

Important:
    This module does NOT classify water quality.
    It only converts visual colour information into
    numerical features.
"""

import cv2
import numpy as np


class ColourFeatureExtractor:
    """
    Extract colour-based statistical features from an image.
    """

    def __init__(self):
        """Initialize the colour feature extractor."""

        self.feature_names = []

    # ========================================================
    # BASIC STATISTICS
    # ========================================================

    @staticmethod
    def _channel_statistics(
        image: np.ndarray,
        prefix: str
    ) -> dict:
        """
        Calculate statistical features for each image channel.

        Features:
            mean
            standard deviation
            median
            minimum
            maximum
        """

        features = {}

        for channel_index in range(
            image.shape[2]
        ):

            channel = image[:, :, channel_index]

            features[
                f"{prefix}_{channel_index + 1}_mean"
            ] = float(
                np.mean(channel)
            )

            features[
                f"{prefix}_{channel_index + 1}_std"
            ] = float(
                np.std(channel)
            )

            features[
                f"{prefix}_{channel_index + 1}_median"
            ] = float(
                np.median(channel)
            )

            features[
                f"{prefix}_{channel_index + 1}_min"
            ] = float(
                np.min(channel)
            )

            features[
                f"{prefix}_{channel_index + 1}_max"
            ] = float(
                np.max(channel)
            )

        return features

    # ========================================================
    # RGB FEATURES
    # ========================================================

    def extract_rgb_features(
        self,
        image_rgb: np.ndarray
    ) -> dict:
        """
        Extract RGB colour statistics.

        Captures:
            - Average colour intensity
            - Colour variation
            - Distribution range
        """

        return self._channel_statistics(
            image_rgb,
            "rgb"
        )

    # ========================================================
    # HSV FEATURES
    # ========================================================

    def extract_hsv_features(
        self,
        image_rgb: np.ndarray
    ) -> dict:
        """
        Convert RGB → HSV and extract statistics.

        HSV separates:
            H = Hue
            S = Saturation
            V = Brightness

        This is useful for identifying changes in water
        coloration and visual appearance.
        """

        image_uint8 = np.asarray(
            image_rgb,
            dtype=np.uint8
        )

        hsv = cv2.cvtColor(
            image_uint8,
            cv2.COLOR_RGB2HSV
        )

        features = {}

        channel_names = [
            "hue",
            "saturation",
            "value"
        ]

        for index, name in enumerate(
            channel_names
        ):

            channel = hsv[:, :, index]

            features[
                f"hsv_{name}_mean"
            ] = float(
                np.mean(channel)
            )

            features[
                f"hsv_{name}_std"
            ] = float(
                np.std(channel)
            )

            features[
                f"hsv_{name}_median"
            ] = float(
                np.median(channel)
            )

            features[
                f"hsv_{name}_min"
            ] = float(
                np.min(channel)
            )

            features[
                f"hsv_{name}_max"
            ] = float(
                np.max(channel)
            )

        return features

    # ========================================================
    # LAB FEATURES
    # ========================================================

    def extract_lab_features(
        self,
        image_rgb: np.ndarray
    ) -> dict:
        """
        Convert RGB → LAB and extract statistics.

        LAB channels:

            L* = Lightness
            a* = Green ↔ Red
            b* = Blue ↔ Yellow

        LAB is useful because colour information is separated
        from lightness more explicitly than RGB.
        """

        image_uint8 = np.asarray(
            image_rgb,
            dtype=np.uint8
        )

        lab = cv2.cvtColor(
            image_uint8,
            cv2.COLOR_RGB2LAB
        )

        features = {}

        channel_names = [
            "lightness",
            "a",
            "b"
        ]

        for index, name in enumerate(
            channel_names
        ):

            channel = lab[:, :, index]

            features[
                f"lab_{name}_mean"
            ] = float(
                np.mean(channel)
            )

            features[
                f"lab_{name}_std"
            ] = float(
                np.std(channel)
            )

            features[
                f"lab_{name}_median"
            ] = float(
                np.median(channel)
            )

            features[
                f"lab_{name}_min"
            ] = float(
                np.min(channel)
            )

            features[
                f"lab_{name}_max"
            ] = float(
                np.max(channel)
            )

        return features

    # ========================================================
    # COLOUR BALANCE
    # ========================================================

    def extract_colour_balance(
        self,
        image_rgb: np.ndarray
    ) -> dict:
        """
        Calculate relative RGB channel relationships.

        These ratios can capture colour casts that may be
        useful when comparing water images.

        Small epsilon prevents division by zero.
        """

        image = image_rgb.astype(
            np.float32
        )

        red = image[:, :, 0]
        green = image[:, :, 1]
        blue = image[:, :, 2]

        red_mean = np.mean(red)
        green_mean = np.mean(green)
        blue_mean = np.mean(blue)

        epsilon = 1e-8

        return {

            "colour_ratio_rg":
                float(
                    red_mean /
                    (green_mean + epsilon)
                ),

            "colour_ratio_rb":
                float(
                    red_mean /
                    (blue_mean + epsilon)
                ),

            "colour_ratio_gb":
                float(
                    green_mean /
                    (blue_mean + epsilon)
                ),

            "colour_cast_blue_red":
                float(
                    blue_mean - red_mean
                ),

            "colour_cast_green_red":
                float(
                    green_mean - red_mean
                ),

        }

    # ========================================================
    # COMPLETE COLOUR FEATURE VECTOR
    # ========================================================

    def extract(
        self,
        image_rgb: np.ndarray
    ) -> dict:
        """
        Extract the complete colour feature set.

        Returns:
            Dictionary containing all colour features.
        """

        if image_rgb is None:
            raise ValueError(
                "Input image cannot be None."
            )

        if image_rgb.ndim != 3:
            raise ValueError(
                "Expected a 3-channel RGB image."
            )

        if image_rgb.shape[2] != 3:
            raise ValueError(
                "Expected RGB image with 3 channels."
            )

        features = {}

        # RGB
        features.update(
            self.extract_rgb_features(
                image_rgb
            )
        )

        # HSV
        features.update(
            self.extract_hsv_features(
                image_rgb
            )
        )

        # LAB
        features.update(
            self.extract_lab_features(
                image_rgb
            )
        )

        # Colour relationships
        features.update(
            self.extract_colour_balance(
                image_rgb
            )
        )

        self.feature_names = list(
            features.keys()
        )

        return features


# ============================================================
# SIMPLE TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("AquaLens AI - Colour Feature Extraction Test")
    print("=" * 60)

    # --------------------------------------------------------
    # Test image
    # --------------------------------------------------------

    test_image_path = (
        "data/raw/UIEB/raw-890/2_img_.png"
    )

    image_bgr = cv2.imread(
        test_image_path
    )

    if image_bgr is None:

        raise FileNotFoundError(
            f"Could not load image:\n"
            f"{test_image_path}"
        )

    # OpenCV → RGB
    image_rgb = cv2.cvtColor(
        image_bgr,
        cv2.COLOR_BGR2RGB
    )

    # --------------------------------------------------------
    # Extract features
    # --------------------------------------------------------

    extractor = ColourFeatureExtractor()

    features = extractor.extract(
        image_rgb
    )

    # --------------------------------------------------------
    # Display results
    # --------------------------------------------------------

    print(
        f"\nImage shape: {image_rgb.shape}"
    )

    print(
        f"Total colour features: "
        f"{len(features)}"
    )

    print("\nExtracted Features:")
    print("-" * 60)

    for name, value in features.items():

        print(
            f"{name:<35} "
            f"{value:.4f}"
        )

    print("\n")
    print("=" * 60)
    print("Colour feature extraction successful!")
    print("=" * 60)