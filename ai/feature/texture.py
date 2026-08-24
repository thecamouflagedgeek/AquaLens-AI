"""
AquaLens AI - Objective 1
Texture Feature Extraction

Purpose:
    Extract quantitative texture characteristics from
    preprocessed water images.

Primary method:
    Gray-Level Co-occurrence Matrix (GLCM)

Texture features:
    - Contrast
    - Dissimilarity
    - Homogeneity
    - Energy
    - Correlation
    - ASM (Angular Second Moment)

Additional statistical descriptors:
    - Intensity variance
    - Intensity range
    - Local intensity variation

IMPORTANT:
    These features describe image texture.
    They do NOT directly identify contamination.

They will later be combined with:
    - Colour features
    - Structural features
    - Other validated visual features

to construct the AquaLens Feature Vector.
"""

import cv2
import numpy as np

from skimage.feature import graycomatrix, graycoprops


class TextureFeatureExtractor:
    """
    Extract texture features from an RGB water image.
    """

    def __init__(
        self,
        levels=32,
        distances=None,
        angles=None
    ):
        """
        Parameters
        ----------
        levels : int
            Number of gray levels used for GLCM.

        distances : list
            Pixel distances used for GLCM.

        angles : list
            Directions used for GLCM.
        """

        self.levels = levels

        if distances is None:
            self.distances = [
                1,
                2,
                4
            ]
        else:
            self.distances = distances

        if angles is None:
            self.angles = [
                0,
                np.pi / 4,
                np.pi / 2,
                3 * np.pi / 4
            ]
        else:
            self.angles = angles

        self.feature_names = []

    # ========================================================
    # IMAGE VALIDATION
    # ========================================================

    @staticmethod
    def _validate_image(image_rgb):
        """
        Validate the input image.
        """

        if image_rgb is None:

            raise ValueError(
                "Input image cannot be None."
            )

        if not isinstance(
            image_rgb,
            np.ndarray
        ):

            raise TypeError(
                "Input image must be a NumPy array."
            )

        if image_rgb.ndim != 3:

            raise ValueError(
                "Expected a 3-dimensional RGB image."
            )

        if image_rgb.shape[2] != 3:

            raise ValueError(
                "Expected an RGB image with 3 channels."
            )

    # ========================================================
    # GRAYSCALE CONVERSION
    # ========================================================

    @staticmethod
    def _to_grayscale(image_rgb):
        """
        Convert RGB image to grayscale.
        """

        return cv2.cvtColor(
            image_rgb,
            cv2.COLOR_RGB2GRAY
        )

    # ========================================================
    # QUANTIZATION
    # ========================================================

    def _quantize_image(self, grayscale):
        """
        Reduce grayscale image to the number of intensity
        levels required by the GLCM.

        Example:
            256 intensity values
                    ↓
                32 levels

        This makes GLCM computation more efficient while
        preserving the overall texture structure.
        """

        grayscale = grayscale.astype(
            np.float32
        )

        quantized = (
            grayscale *
            self.levels /
            256.0
        ).astype(np.uint8)

        quantized = np.clip(
            quantized,
            0,
            self.levels - 1
        )

        return quantized

    # ========================================================
    # GLCM
    # ========================================================

    def _calculate_glcm(
        self,
        quantized
    ):
        """
        Construct the Gray-Level Co-occurrence Matrix.
        """

        glcm = graycomatrix(
            quantized,
            distances=self.distances,
            angles=self.angles,
            levels=self.levels,
            symmetric=True,
            normed=True
        )

        return glcm

    # ========================================================
    # GLCM FEATURES
    # ========================================================

    def extract_glcm_features(
        self,
        grayscale
    ):
        """
        Extract standard GLCM texture properties.

        Properties:
            contrast
            dissimilarity
            homogeneity
            energy
            correlation
            ASM

        Results are averaged across all configured
        distances and angles.
        """

        quantized = self._quantize_image(
            grayscale
        )

        glcm = self._calculate_glcm(
            quantized
        )

        properties = [
            "contrast",
            "dissimilarity",
            "homogeneity",
            "energy",
            "correlation",
            "ASM"
        ]

        features = {}

        for property_name in properties:

            values = graycoprops(
                glcm,
                property_name
            )

            features[
                f"glcm_{property_name.lower()}_mean"
            ] = float(
                np.mean(values)
            )

            features[
                f"glcm_{property_name.lower()}_std"
            ] = float(
                np.std(values)
            )

            features[
                f"glcm_{property_name.lower()}_min"
            ] = float(
                np.min(values)
            )

            features[
                f"glcm_{property_name.lower()}_max"
            ] = float(
                np.max(values)
            )

        return features

    # ========================================================
    # INTENSITY STATISTICS
    # ========================================================

    @staticmethod
    def extract_intensity_features(
        grayscale
    ):
        """
        Extract basic intensity variation measures.

        These are simple texture-related descriptors and
        complement the GLCM features.
        """

        mean_intensity = np.mean(
            grayscale
        )

        std_intensity = np.std(
            grayscale
        )

        variance = np.var(
            grayscale
        )

        intensity_range = (
            np.max(grayscale) -
            np.min(grayscale)
        )

        return {

            "texture_intensity_mean":
                float(mean_intensity),

            "texture_intensity_std":
                float(std_intensity),

            "texture_intensity_variance":
                float(variance),

            "texture_intensity_range":
                float(intensity_range),
        }

    # ========================================================
    # LOCAL VARIATION
    # ========================================================

    @staticmethod
    def extract_local_variation(
        grayscale
    ):
        """
        Measure local pixel-to-pixel variation.

        A 3x3 local standard deviation map is used to
        estimate how much intensity changes within local
        neighborhoods.

        This can help distinguish smoother regions from
        highly variable regions.
        """

        image_float = grayscale.astype(
            np.float32
        )

        mean = cv2.blur(
            image_float,
            (3, 3)
        )

        squared_mean = cv2.blur(
            image_float ** 2,
            (3, 3)
        )

        local_variance = (
            squared_mean -
            mean ** 2
        )

        local_variance = np.maximum(
            local_variance,
            0
        )

        local_std = np.sqrt(
            local_variance
        )

        return {

            "local_variation_mean":
                float(
                    np.mean(local_std)
                ),

            "local_variation_std":
                float(
                    np.std(local_std)
                ),

            "local_variation_max":
                float(
                    np.max(local_std)
                ),
        }

    # ========================================================
    # COMPLETE TEXTURE FEATURE VECTOR
    # ========================================================

    def extract(
        self,
        image_rgb
    ):
        """
        Extract the complete texture feature set.

        Returns
        -------
        dict
            Dictionary containing all texture features.
        """

        self._validate_image(
            image_rgb
        )

        grayscale = self._to_grayscale(
            image_rgb
        )

        features = {}

        # ----------------------------------------------------
        # GLCM
        # ----------------------------------------------------

        features.update(
            self.extract_glcm_features(
                grayscale
            )
        )

        # ----------------------------------------------------
        # Intensity statistics
        # ----------------------------------------------------

        features.update(
            self.extract_intensity_features(
                grayscale
            )
        )

        # ----------------------------------------------------
        # Local variation
        # ----------------------------------------------------

        features.update(
            self.extract_local_variation(
                grayscale
            )
        )

        self.feature_names = list(
            features.keys()
        )

        return features


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print(
        "AquaLens AI - Texture Feature Extraction Test"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Test image
    # --------------------------------------------------------

    image_path = (
        "data/raw/UIEB/raw-890/2_img_.png"
    )

    image_bgr = cv2.imread(
        image_path
    )

    if image_bgr is None:

        raise FileNotFoundError(
            f"\nCould not load image:\n{image_path}"
        )

    # OpenCV BGR → RGB
    image_rgb = cv2.cvtColor(
        image_bgr,
        cv2.COLOR_BGR2RGB
    )

    # --------------------------------------------------------
    # Extract features
    # --------------------------------------------------------

    extractor = TextureFeatureExtractor()

    features = extractor.extract(
        image_rgb
    )

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print(
        f"\nImage shape: "
        f"{image_rgb.shape}"
    )

    print(
        f"Total texture features: "
        f"{len(features)}"
    )

    print("\nExtracted Features:")
    print("-" * 70)

    for name, value in features.items():

        print(
            f"{name:<45}"
            f"{value:.6f}"
        )

    print("\n")
    print("=" * 70)
    print(
        "Texture feature extraction successful!"
    )
    print("=" * 70)