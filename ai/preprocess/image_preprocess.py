"""
AquaLens AI - Objective 1
Image Preprocessing Module

Pipeline:

Raw Image
    ↓
Validation
    ↓
Resize
    ↓
Denoising
    ↓
RGB
    ↓
HSV / LAB
    ↓
Illumination & Contrast Normalization
    ↓
Preprocessed Image Representations

Important:
- Original images are NEVER modified.
- This module is dataset-independent.
- The same preprocessing interface can later be used
  with Raspberry Pi camera frames.
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

@dataclass
class PreprocessingConfig:

    # Standard processing resolution
    width: int = 256
    height: int = 256

    # Denoising
    denoise_enabled: bool = True
    denoise_method: str = "gaussian"

    # Gaussian blur
    gaussian_kernel_size: int = 5
    gaussian_sigma: float = 0.0

    # Median filtering
    median_kernel_size: int = 5

    # Contrast / illumination normalization
    normalization_enabled: bool = True
    normalization_method: str = "clahe"

    # CLAHE
    clahe_clip_limit: float = 2.0
    clahe_grid_size: tuple = (8, 8)

@dataclass
class PreprocessedImage:
    original: np.ndarray
    resized: np.ndarray
    denoised: np.ndarray
    normalized: np.ndarray

    hsv: np.ndarray
    lab: np.ndarray
    grayscale: np.ndarray

class ImagePreprocessor:

    def __init__(
        self,
        config: Optional[PreprocessingConfig] = None
    ):
        self.config = config or PreprocessingConfig()

        self._validate_config()


    def _validate_config(self) -> None:
        if self.config.width <= 0:
            raise ValueError("Image width must be positive.")

        if self.config.height <= 0:
            raise ValueError("Image height must be positive.")

        if self.config.denoise_method not in {
            "gaussian",
            "median",
            "none",
        }:
            raise ValueError(
                "Unsupported denoise method. "
                "Use: gaussian, median, or none."
            )

        if self.config.normalization_method not in {
            "clahe",
            "histogram",
            "none",
        }:
            raise ValueError(
                "Unsupported normalization method. "
                "Use: clahe, histogram, or none."
            )

        if self.config.gaussian_kernel_size % 2 == 0:
            raise ValueError(
                "Gaussian kernel size must be odd."
            )

        if self.config.median_kernel_size % 2 == 0:
            raise ValueError(
                "Median kernel size must be odd."
            )


    @staticmethod
    def load_image(image_path: str) -> np.ndarray:
        image = cv2.imread(
            image_path,
            cv2.IMREAD_COLOR
        )

        if image is None:
            raise FileNotFoundError(
                f"Unable to read image: {image_path}"
            )

        return image

    def resize(self, image: np.ndarray) -> np.ndarray:
        return cv2.resize(
            image,
            (
                self.config.width,
                self.config.height
            ),
            interpolation=cv2.INTER_AREA
        )

    def denoise(self, image: np.ndarray) -> np.ndarray:

        if not self.config.denoise_enabled:
            return image.copy()

        method = self.config.denoise_method

        if method == "gaussian":

            return cv2.GaussianBlur(
                image,
                (
                    self.config.gaussian_kernel_size,
                    self.config.gaussian_kernel_size,
                ),
                self.config.gaussian_sigma,
            )

        if method == "median":

            return cv2.medianBlur(
                image,
                self.config.median_kernel_size
            )

        return image.copy()

    @staticmethod
    def to_rgb(image: np.ndarray) -> np.ndarray:
        """
        Convert OpenCV BGR image to RGB.
        """

        return cv2.cvtColor(
            image,
            cv2.COLOR_BGR2RGB
        )

    @staticmethod
    def to_hsv(image_rgb: np.ndarray) -> np.ndarray:
        """
        Convert RGB image to HSV colour space.
        """

        return cv2.cvtColor(
            image_rgb,
            cv2.COLOR_RGB2HSV
        )

    @staticmethod
    def to_lab(image_rgb: np.ndarray) -> np.ndarray:
        """
        Convert RGB image to CIE LAB colour space.

        LAB is useful for separating luminance from
        chromatic information.
        """

        return cv2.cvtColor(
            image_rgb,
            cv2.COLOR_RGB2LAB
        )


    @staticmethod
    def to_grayscale(image_rgb: np.ndarray) -> np.ndarray:
        """
        Convert RGB image to grayscale.

        Used later for:
        - texture analysis
        - edge detection
        - Laplacian variance
        """

        return cv2.cvtColor(
            image_rgb,
            cv2.COLOR_RGB2GRAY
        )

    # ========================================================
    # CLAHE
    # ========================================================

    def apply_clahe(
        self,
        image_rgb: np.ndarray
    ) -> np.ndarray:
        """
        Apply CLAHE to the luminance channel.

        Instead of independently modifying RGB channels,
        CLAHE is applied to the L channel of LAB.

        This helps avoid unnecessary colour distortion.
        """

        lab = cv2.cvtColor(
            image_rgb,
            cv2.COLOR_RGB2LAB
        )

        l_channel, a_channel, b_channel = cv2.split(lab)

        clahe = cv2.createCLAHE(
            clipLimit=self.config.clahe_clip_limit,
            tileGridSize=self.config.clahe_grid_size,
        )

        enhanced_l = clahe.apply(l_channel)

        enhanced_lab = cv2.merge(
            (
                enhanced_l,
                a_channel,
                b_channel,
            )
        )

        enhanced_rgb = cv2.cvtColor(
            enhanced_lab,
            cv2.COLOR_LAB2RGB
        )

        return enhanced_rgb


    @staticmethod
    def apply_histogram_normalization(
        image_rgb: np.ndarray
    ) -> np.ndarray:
        """
        Apply histogram equalization to the luminance channel.

        LAB is used so that colour channels are not independently
        distorted.
        """

        lab = cv2.cvtColor(
            image_rgb,
            cv2.COLOR_RGB2LAB
        )

        l_channel, a_channel, b_channel = cv2.split(lab)

        equalized_l = cv2.equalizeHist(
            l_channel
        )

        equalized_lab = cv2.merge(
            (
                equalized_l,
                a_channel,
                b_channel,
            )
        )

        return cv2.cvtColor(
            equalized_lab,
            cv2.COLOR_LAB2RGB
        )

    def normalize(
        self,
        image_rgb: np.ndarray
    ) -> np.ndarray:
        """
        Apply the configured illumination / contrast
        normalization method.
        """

        if not self.config.normalization_enabled:
            return image_rgb.copy()

        method = self.config.normalization_method

        if method == "clahe":
            return self.apply_clahe(image_rgb)

        if method == "histogram":
            return self.apply_histogram_normalization(
                image_rgb
            )

        return image_rgb.copy()


    def process(
        self,
        image: np.ndarray
    ) -> PreprocessedImage:
        """
        Run the complete preprocessing pipeline.

        Pipeline:

        Input
          ↓
        Resize
          ↓
        Denoise
          ↓
        RGB
          ↓
        Normalization
          ↓
        HSV + LAB
          ↓
        Grayscale
        """

        if image is None:
            raise ValueError(
                "Input image cannot be None."
            )

        # Preserve original image
        original = image.copy()

        # Step 1: Resize
        resized_bgr = self.resize(image)

        # Step 2: Denoising
        denoised_bgr = self.denoise(
            resized_bgr
        )

        # Step 3: Convert BGR → RGB
        denoised_rgb = self.to_rgb(
            denoised_bgr
        )

        # Step 4: Illumination / contrast normalization
        normalized_rgb = self.normalize(
            denoised_rgb
        )

        # Step 5: Generate colour representations
        hsv = self.to_hsv(
            normalized_rgb
        )

        lab = self.to_lab(
            normalized_rgb
        )

        # Step 6: Grayscale
        grayscale = self.to_grayscale(
            normalized_rgb
        )

        return PreprocessedImage(
            original=original,
            resized=self.to_rgb(resized_bgr),
            denoised=denoised_rgb,
            normalized=normalized_rgb,
            hsv=hsv,
            lab=lab,
            grayscale=grayscale,
        )

def save_rgb_image(
    image_rgb: np.ndarray,
    output_path: str
) -> None:
    """
    Save an RGB image correctly using OpenCV.

    OpenCV expects BGR when writing images.
    """

    image_bgr = cv2.cvtColor(
        image_rgb,
        cv2.COLOR_RGB2BGR
    )

    success = cv2.imwrite(
        output_path,
        image_bgr
    )

    if not success:
        raise IOError(
            f"Failed to save image: {output_path}"
        )


if __name__ == "__main__":

    image_path = (
        "data/raw/UIEB/raw-890/2_img_.png"
    )

    config = PreprocessingConfig(
        width=256,
        height=256,
        denoise_enabled=True,
        denoise_method="gaussian",
        normalization_enabled=True,
        normalization_method="clahe",
    )

    preprocessor = ImagePreprocessor(
        config=config
    )

    image = preprocessor.load_image(
        image_path
    )

    result = preprocessor.process(
        image
    )

    print("Preprocessing successful!")

    print(
        "Original:",
        result.original.shape
    )

    print(
        "Resized:",
        result.resized.shape
    )

    print(
        "Denoised:",
        result.denoised.shape
    )

    print(
        "Normalized:",
        result.normalized.shape
    )

    print(
        "HSV:",
        result.hsv.shape
    )

    print(
        "LAB:",
        result.lab.shape
    )

    print(
        "Grayscale:",
        result.grayscale.shape
    )