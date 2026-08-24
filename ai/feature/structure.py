"""
AquaLens AI - Objective 1
Structural Feature Extraction

Purpose:
    Extract spatial and structural characteristics from
    water images.

These features describe:
        - Visible edges
        - Image sharpness
        - Gradient structure
        - Connected regions
        - Visible particle-like structures

IMPORTANT:
    This module does NOT classify contamination.
    It only converts structural visual information into
    numerical features.

These features will later be combined with:
        Colour Features
        Texture Features
        Intensity Features

to form the AquaLens Feature Vector.
"""

import cv2
import numpy as np


class StructuralFeatureExtractor:
    """
    Extract structural features from an RGB water image.
    """

    def __init__(
        self,
        canny_low=50,
        canny_high=150,
        min_component_area=10
    ):
        """
        Parameters
        ----------
        canny_low : int
            Lower threshold for Canny edge detection.

        canny_high : int
            Upper threshold for Canny edge detection.

        min_component_area : int
            Minimum connected-component area considered
            as a meaningful region.
        """

        self.canny_low = canny_low
        self.canny_high = canny_high
        self.min_component_area = min_component_area

        self.feature_names = []

    # ========================================================
    # IMAGE VALIDATION
    # ========================================================

    @staticmethod
    def _validate_image(image_rgb):
        """
        Validate input image.
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
    # GRAYSCALE
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
    # EDGE FEATURES
    # ========================================================

    def extract_edge_features(
        self,
        grayscale
    ):
        """
        Extract edge-related features.

        Features:
            edge_density
            mean_edge_strength
            edge_pixel_count

        Edge density represents the proportion of pixels
        belonging to detected edges.
        """

        edges = cv2.Canny(
            grayscale,
            self.canny_low,
            self.canny_high
        )

        edge_pixels = np.count_nonzero(
            edges
        )

        total_pixels = edges.size

        edge_density = (
            edge_pixels /
            total_pixels
        )

        # Sobel gradient magnitude
        gradient_x = cv2.Sobel(
            grayscale,
            cv2.CV_64F,
            1,
            0,
            ksize=3
        )

        gradient_y = cv2.Sobel(
            grayscale,
            cv2.CV_64F,
            0,
            1,
            ksize=3
        )

        gradient_magnitude = np.sqrt(
            gradient_x ** 2 +
            gradient_y ** 2
        )

        if edge_pixels > 0:

            edge_strength = float(
                np.mean(
                    gradient_magnitude[
                        edges > 0
                    ]
                )
            )

        else:

            edge_strength = 0.0

        return {
            "edge_density":
                float(edge_density),

            "edge_pixel_count":
                int(edge_pixels),

            "mean_edge_strength":
                edge_strength,
        }

    # ========================================================
    # GRADIENT FEATURES
    # ========================================================

    def extract_gradient_features(
        self,
        grayscale
    ):
        """
        Extract image gradient characteristics.

        Gradients describe how rapidly image intensity
        changes across neighboring pixels.
        """

        gradient_x = cv2.Sobel(
            grayscale,
            cv2.CV_64F,
            1,
            0,
            ksize=3
        )

        gradient_y = cv2.Sobel(
            grayscale,
            cv2.CV_64F,
            0,
            1,
            ksize=3
        )

        magnitude = np.sqrt(
            gradient_x ** 2 +
            gradient_y ** 2
        )

        orientation = np.arctan2(
            gradient_y,
            gradient_x
        )

        return {
            "gradient_mean":
                float(
                    np.mean(magnitude)
                ),

            "gradient_std":
                float(
                    np.std(magnitude)
                ),

            "gradient_max":
                float(
                    np.max(magnitude)
                ),

            "gradient_orientation_mean":
                float(
                    np.mean(orientation)
                ),

            "gradient_orientation_std":
                float(
                    np.std(orientation)
                ),
        }

    # ========================================================
    # SHARPNESS
    # ========================================================

    @staticmethod
    def extract_sharpness_features(
        grayscale
    ):
        """
        Measure image sharpness using Laplacian variance.

        Higher variance generally indicates stronger
        high-frequency detail / sharper structures.

        Lower variance generally indicates a smoother
        or blurrier image.
        """

        laplacian = cv2.Laplacian(
            grayscale,
            cv2.CV_64F
        )

        variance = np.var(
            laplacian
        )

        return {
            "laplacian_variance":
                float(variance)
        }

    # ========================================================
    # CONNECTED COMPONENT FEATURES
    # ========================================================

    def extract_component_features(
        self,
        grayscale
    ):
        """
        Detect connected regions from a binary representation.

        NOTE:
            This is a candidate structural descriptor.
            It does NOT mean that every detected region is
            a real contaminant or particle.
        """

        # Otsu thresholding
        _, binary = cv2.threshold(
            grayscale,
            0,
            255,
            cv2.THRESH_BINARY +
            cv2.THRESH_OTSU
        )

        # Remove very small noise
        kernel = np.ones(
            (3, 3),
            np.uint8
        )

        cleaned = cv2.morphologyEx(
            binary,
            cv2.MORPH_OPEN,
            kernel
        )

        num_labels, labels, stats, _ = (
            cv2.connectedComponentsWithStats(
                cleaned,
                connectivity=8
            )
        )

        areas = []

        for label in range(
            1,
            num_labels
        ):

            area = stats[
                label,
                cv2.CC_STAT_AREA
            ]

            if area >= self.min_component_area:

                areas.append(
                    area
                )

        if len(areas) == 0:

            return {
                "component_count": 0,
                "component_area_mean": 0.0,
                "component_area_std": 0.0,
                "largest_component_area": 0.0,
                "component_area_ratio": 0.0,
            }

        areas = np.asarray(
            areas,
            dtype=np.float64
        )

        total_pixels = (
            grayscale.shape[0] *
            grayscale.shape[1]
        )

        return {
            "component_count":
                int(len(areas)),

            "component_area_mean":
                float(np.mean(areas)),

            "component_area_std":
                float(np.std(areas)),

            "largest_component_area":
                float(np.max(areas)),

            "component_area_ratio":
                float(
                    np.sum(areas) /
                    total_pixels
                ),
        }

    # ========================================================
    # CONTOUR FEATURES
    # ========================================================

    def extract_contour_features(
        self,
        grayscale
    ):
        """
        Extract basic contour characteristics.

        Contours describe boundaries of visible regions.
        """

        _, binary = cv2.threshold(
            grayscale,
            0,
            255,
            cv2.THRESH_BINARY +
            cv2.THRESH_OTSU
        )

        contours, _ = cv2.findContours(
            binary,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        valid_contours = []

        for contour in contours:

            area = cv2.contourArea(
                contour
            )

            if area >= self.min_component_area:

                valid_contours.append(
                    contour
                )

        if not valid_contours:

            return {
                "contour_count": 0,
                "contour_area_mean": 0.0,
                "contour_area_std": 0.0,
                "largest_contour_area": 0.0,
            }

        areas = np.asarray(
            [
                cv2.contourArea(c)
                for c in valid_contours
            ],
            dtype=np.float64
        )

        return {
            "contour_count":
                int(len(areas)),

            "contour_area_mean":
                float(np.mean(areas)),

            "contour_area_std":
                float(np.std(areas)),

            "largest_contour_area":
                float(np.max(areas)),
        }

    # ========================================================
    # COMPLETE STRUCTURAL FEATURE VECTOR
    # ========================================================

    def extract(
        self,
        image_rgb
    ):
        """
        Extract the complete structural feature set.

        Returns
        -------
        dict
            Dictionary containing structural features.
        """

        self._validate_image(
            image_rgb
        )

        grayscale = self._to_grayscale(
            image_rgb
        )

        features = {}

        # Edge information
        features.update(
            self.extract_edge_features(
                grayscale
            )
        )

        # Gradient information
        features.update(
            self.extract_gradient_features(
                grayscale
            )
        )

        # Sharpness
        features.update(
            self.extract_sharpness_features(
                grayscale
            )
        )

        # Connected regions
        features.update(
            self.extract_component_features(
                grayscale
            )
        )

        # Contours
        features.update(
            self.extract_contour_features(
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

    print("=" * 65)
    print(
        "AquaLens AI - Structural Feature Extraction Test"
    )
    print("=" * 65)

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

    extractor = StructuralFeatureExtractor()

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
        f"Total structural features: "
        f"{len(features)}"
    )

    print("\nExtracted Features:")
    print("-" * 65)

    for name, value in features.items():

        print(
            f"{name:<40}"
            f"{value:.6f}"
        )

    print("\n")
    print("=" * 65)
    print(
        "Structural feature extraction successful!"
    )
    print("=" * 65)