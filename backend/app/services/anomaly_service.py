"""
AquaLens AI - Anomaly Detection Service
Compares observation feature vectors against station-specific robust baselines.
Explains deviations on a per-feature basis and separates normal variation,
potential anomalies, and persistent anomalies without claiming pollution proof.
"""

import json
from typing import Dict, Any, List, Optional
import numpy as np
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.models import (
    Observation,
    FeatureVector,
    SourceBaseline,
    AnomalyResult,
)
from ..ml.feature_schema import FEATURE_NAMES

EPS = 1e-6


class AnomalyService:
    @classmethod
    def analyze_observation(
        cls,
        db: Session,
        observation: Observation,
        baseline: Optional[SourceBaseline] = None,
    ) -> AnomalyResult:
        """
        Runs source-specific anomaly detection on an observation.
        If baseline is missing or status != 'established', returns an unassessed anomaly record.
        """
        if not observation.feature_vector:
            raise ValueError(f"Observation {observation.id} has no extracted feature vector.")

        # If baseline not explicitly passed, find latest active for station
        if baseline is None:
            baseline = (
                db.query(SourceBaseline)
                .filter(
                    SourceBaseline.station_id == observation.station_id,
                    SourceBaseline.status == "established",
                )
                .order_by(SourceBaseline.id.desc())
                .first()
            )

        features = observation.feature_vector.get_features()

        # If no established baseline exists, return unassessed result
        if not baseline or baseline.status != "established" or not baseline.stats_json:
            unassessed = AnomalyResult(
                observation_id=observation.id,
                baseline_id=baseline.id if baseline else None,
                overall_anomaly_score=None,
                status="unassessed",
                threshold_used=settings.ANOMALY_Z_THRESHOLD,
                methodology="robust-z-mad",
                deviations_json=json.dumps({}),
                top_contributors_json=json.dumps([]),
                warnings_json=json.dumps(["Baseline unestablished or insufficient data for station."]),
            )
            return unassessed

        baseline_stats = baseline.get_stats()
        deviations = {}
        z_scores = []
        top_candidates = []

        threshold = settings.ANOMALY_Z_THRESHOLD

        for feature_name in FEATURE_NAMES:
            stat = baseline_stats.get(feature_name)
            if not stat:
                continue

            obs_val = float(features.get(feature_name, 0.0))
            med = float(stat.get("median", 0.0))
            mad = float(stat.get("mad", 0.0))

            # Robust scale estimate: 1.4826 * MAD approximates standard deviation for normal dist
            scale = 1.4826 * mad
            if scale < EPS:
                # If MAD is near zero, use IQR / 1.349 or EPS
                iqr = float(stat.get("iqr", 0.0))
                scale = (iqr / 1.349) if iqr > EPS else 1.0

            robust_z = float(abs(obs_val - med) / scale)
            is_deviated = bool(robust_z >= threshold)

            deviations[feature_name] = {
                "feature_name": feature_name,
                "observed_value": round(obs_val, 4),
                "baseline_median": round(med, 4),
                "baseline_mad": round(mad, 4),
                "robust_z_score": round(robust_z, 4),
                "is_deviated": is_deviated,
            }
            z_scores.append(robust_z)
            top_candidates.append((feature_name, robust_z))

        # Overall anomaly score: combination of top feature deviation and multi-feature shift
        if z_scores:
            top_k_mean = float(np.mean(sorted(z_scores, reverse=True)[:3]))
            p75 = float(np.percentile(z_scores, 75))
            overall_score = float(round(0.6 * top_k_mean + 0.4 * p75, 4))
        else:
            overall_score = 0.0

        # Sort top contributing deviations
        top_candidates.sort(key=lambda x: x[1], reverse=True)
        top_contributors = [name for name, z in top_candidates[:5] if z >= (threshold * 0.75)]

        # Determine anomaly condition: triggers if overall score >= threshold or acute spike (>= threshold * 1.5)
        max_z = max(z_scores) if z_scores else 0.0
        is_anomalous = bool((overall_score >= threshold) or (max_z >= threshold * 1.5))

        # Check previous observation for persistence
        status = "normal_variation"
        if is_anomalous:
            prev_obs = (
                db.query(Observation)
                .join(AnomalyResult, AnomalyResult.observation_id == Observation.id)
                .filter(
                    Observation.station_id == observation.station_id,
                    Observation.id < observation.id,
                )
                .order_by(Observation.id.desc())
                .first()
            )
            if prev_obs and prev_obs.anomaly_result and prev_obs.anomaly_result.status in ["potential_anomaly", "persistent_anomaly"]:
                status = "persistent_anomaly"
            else:
                status = "potential_anomaly"

        # Quality-control warnings
        qc_warnings = []
        if observation.illumination_condition in ["DirectSun", "Artificial"]:
            qc_warnings.append(f"Non-standard illumination ({observation.illumination_condition}) may alter visual colour descriptors.")
        if "texture_intensity_variance" in top_contributors and deviations["texture_intensity_variance"]["observed_value"] > 5000:
            qc_warnings.append("High texture variance detected; possible camera glare, water surface ripple, or particulate matter.")

        anomaly_result = AnomalyResult(
            observation_id=observation.id,
            baseline_id=baseline.id,
            overall_anomaly_score=overall_score,
            status=status,
            threshold_used=threshold,
            methodology="robust-z-mad",
            deviations_json=json.dumps(deviations),
            top_contributors_json=json.dumps(top_contributors),
            warnings_json=json.dumps(qc_warnings),
        )
        return anomaly_result

    @classmethod
    def save_or_update_anomaly(
        cls,
        db: Session,
        observation: Observation,
        baseline: Optional[SourceBaseline] = None,
    ) -> AnomalyResult:
        result = cls.analyze_observation(db, observation, baseline)
        existing = db.query(AnomalyResult).filter(AnomalyResult.observation_id == observation.id).first()
        if existing:
            existing.baseline_id = result.baseline_id
            existing.overall_anomaly_score = result.overall_anomaly_score
            existing.status = result.status
            existing.threshold_used = result.threshold_used
            existing.methodology = result.methodology
            existing.deviations_json = result.deviations_json
            existing.top_contributors_json = result.top_contributors_json
            existing.warnings_json = result.warnings_json
            db.commit()
            db.refresh(existing)
            return existing
        else:
            db.add(result)
            db.commit()
            db.refresh(result)
            return result
