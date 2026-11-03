"""
AquaLens AI - Objective 2 Model Inference Engine
Integrates the trained Random Forest classifier, StandardScaler, and LabelEncoder.
Preserves model traceability, feature names and ordering, and calibrated probability limitations.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import joblib
import numpy as np

from .feature_schema import FEATURE_NAMES

# Model paths
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
RF_MODEL_PATH = ARTIFACTS_DIR / "AquaLens_RF_Baseline_20Features.joblib"
SCALER_PATH = ARTIFACTS_DIR / "AquaLens_20Feature_Scaler.joblib"
LABEL_ENCODER_PATH = ARTIFACTS_DIR / "AquaLens_LabelEncoder.joblib"

MODEL_VERSION = "rf-baseline-20feat-v1.0.0"
FEATURE_EXTRACTOR_VERSION = "opencv-20feat-v1.0.0"


class InferenceEngine:
    _instance = None

    def __init__(self):
        self.model = None
        self.scaler = None
        self.label_encoder = None
        self.classes_ = []
        self.is_loaded = False
        self.load_error = None
        self._load_artifacts()

    def _load_artifacts(self):
        try:
            if not RF_MODEL_PATH.exists():
                raise FileNotFoundError(f"Random Forest artifact not found at {RF_MODEL_PATH}")
            if not SCALER_PATH.exists():
                raise FileNotFoundError(f"Scaler artifact not found at {SCALER_PATH}")
            if not LABEL_ENCODER_PATH.exists():
                raise FileNotFoundError(f"Label encoder artifact not found at {LABEL_ENCODER_PATH}")

            self.model = joblib.load(RF_MODEL_PATH)
            self.scaler = joblib.load(SCALER_PATH)
            self.label_encoder = joblib.load(LABEL_ENCODER_PATH)
            self.classes_ = list(self.label_encoder.classes_)
            self.is_loaded = True
        except Exception as e:
            self.is_loaded = False
            self.load_error = str(e)

    def classify_vector(self, feature_vector: np.ndarray) -> Dict[str, Any]:
        """
        Runs inference on a 20-dimensional feature vector.
        Vector must be in the exact order of FEATURE_NAMES.
        """
        if not self.is_loaded:
            raise RuntimeError(f"Classifier artifacts unavailable: {self.load_error}")

        vec = np.asarray(feature_vector, dtype=np.float32)
        if vec.ndim == 1:
            if vec.shape[0] != len(FEATURE_NAMES):
                raise ValueError(f"Expected {len(FEATURE_NAMES)} features, got {vec.shape[0]}")
            vec = vec.reshape(1, -1)

        # Apply scaling
        vec_scaled = self.scaler.transform(vec)

        # Run inference
        predicted_idx = self.model.predict(vec_scaled)[0]
        predicted_label = str(self.label_encoder.inverse_transform([predicted_idx])[0])

        # Raw forest probabilities (NOT calibrated confidence)
        raw_probs = self.model.predict_proba(vec_scaled)[0]
        prob_dict = {
            cls_name: float(round(prob, 4))
            for cls_name, prob in zip(self.classes_, raw_probs)
        }

        # Model feature importances for explainability
        feature_importances = {}
        if hasattr(self.model, "feature_importances_"):
            for fname, imp in zip(FEATURE_NAMES, self.model.feature_importances_):
                feature_importances[fname] = float(round(imp, 5))

        return {
            "predicted_condition": predicted_label,
            "raw_probabilities": prob_dict,
            "probability_note": "Raw tree-vote probabilities; not calibrated confidence.",
            "model_version": MODEL_VERSION,
            "feature_extractor_version": FEATURE_EXTRACTOR_VERSION,
            "feature_importances": feature_importances,
            "disclaimer": (
                "Classification describes visual turbidity/condition categories (Low/Medium/High). "
                "It does not assess potability, bacteriological contamination, or chemical safety."
            ),
        }

    def classify_dict(self, features_dict: Dict[str, float]) -> Dict[str, Any]:
        missing = [f for f in FEATURE_NAMES if f not in features_dict]
        if missing:
            raise ValueError(f"Missing required features: {missing}")

        vector = np.array([float(features_dict[f]) for f in FEATURE_NAMES], dtype=np.float32)
        result = self.classify_vector(vector)
        result["extracted_features"] = {f: float(features_dict[f]) for f in FEATURE_NAMES}
        return result


# Global singleton
_inference_engine: Optional[InferenceEngine] = None


def get_inference_engine() -> InferenceEngine:
    global _inference_engine
    if _inference_engine is None:
        _inference_engine = InferenceEngine()
    return _inference_engine
