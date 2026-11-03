"""
AquaLens AI - Source-Specific Baseline (Water Fingerprint) Service
Calculates robust statistics (median, IQR, MAD) over a station's historical observations.
Enforces strict sufficiency rules (does not fabricate baselines from insufficient samples).
"""

from datetime import datetime, timezone
import json
from typing import Dict, Any, List, Optional
import numpy as np
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.models import (
    MonitoringStation,
    Observation,
    FeatureVector,
    SourceBaseline,
    AuditLog,
)
from ..ml.feature_schema import FEATURE_NAMES

EPS = 1e-6


class FingerprintService:
    @staticmethod
    def calculate_robust_feature_stats(observations_features: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        """
        Calculates median, IQR (q75 - q25), and MAD (Median Absolute Deviation)
        for each of the 20 features across the given observation sample set.
        """
        stats_by_feature = {}
        for feature_name in FEATURE_NAMES:
            values = np.array([float(obs[feature_name]) for obs in observations_features if feature_name in obs], dtype=np.float64)
            values = values[np.isfinite(values)]

            if len(values) == 0:
                stats_by_feature[feature_name] = {
                    "median": 0.0,
                    "q25": 0.0,
                    "q75": 0.0,
                    "iqr": 0.0,
                    "mad": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                }
                continue

            med = float(np.median(values))
            q25 = float(np.percentile(values, 25))
            q75 = float(np.percentile(values, 75))
            iqr = float(max(q75 - q25, 0.0))
            mad = float(np.median(np.abs(values - med)))

            stats_by_feature[feature_name] = {
                "median": round(med, 5),
                "q25": round(q25, 5),
                "q75": round(q75, 5),
                "iqr": round(iqr, 5),
                "mad": round(mad, 5),
                "min": round(float(np.min(values)), 5),
                "max": round(float(np.max(values)), 5),
            }

        return stats_by_feature

    @classmethod
    def build_or_update_baseline(
        cls,
        db: Session,
        station_id: int,
        min_samples: Optional[int] = None,
        notes: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> SourceBaseline:
        """
        Constructs a source-specific baseline for the given station.
        If sample count is below threshold, marks baseline status as 'insufficient_data'.
        """
        threshold = min_samples or settings.BASELINE_MIN_OBSERVATIONS

        station = db.query(MonitoringStation).filter(MonitoringStation.id == station_id).first()
        if not station:
            raise ValueError(f"Monitoring station {station_id} not found.")

        # Query eligible observations that have feature vectors
        observations = (
            db.query(Observation)
            .filter(
                Observation.station_id == station_id,
                Observation.is_eligible_for_baseline == True,
            )
            .order_by(Observation.sampling_timestamp.asc())
            .all()
        )

        obs_features = []
        timestamps = []
        for obs in observations:
            if obs.feature_vector:
                obs_features.append(obs.feature_vector.get_features())
                timestamps.append(obs.sampling_timestamp)

        sample_count = len(obs_features)

        # Archive any previous active baseline
        existing_active = (
            db.query(SourceBaseline)
            .filter(
                SourceBaseline.station_id == station_id,
                SourceBaseline.status.in_(["established", "insufficient_data"]),
            )
            .all()
        )
        for prev in existing_active:
            prev.status = "archived"

        # Check sufficiency
        if sample_count < threshold:
            baseline = SourceBaseline(
                station_id=station_id,
                version=f"v{len(existing_active) + 1}.0.0-provisional",
                status="insufficient_data",
                sample_count=sample_count,
                start_date=timestamps[0] if timestamps else None,
                end_date=timestamps[-1] if timestamps else None,
                methodology="robust-median-iqr-mad",
                stats_json=json.dumps({}),
                notes=(
                    f"Baseline unestablished: only {sample_count} eligible observation(s) recorded. "
                    f"A minimum of {threshold} validated observations is required."
                ),
            )
        else:
            stats = cls.calculate_robust_feature_stats(obs_features)
            baseline = SourceBaseline(
                station_id=station_id,
                version=f"v{len(existing_active) + 1}.0.0",
                status="established",
                sample_count=sample_count,
                start_date=timestamps[0],
                end_date=timestamps[-1],
                methodology="robust-median-iqr-mad",
                stats_json=json.dumps(stats),
                notes=notes or f"Baseline constructed from {sample_count} validated observations.",
            )

        db.add(baseline)
        db.flush()

        # Audit log entry
        audit = AuditLog(
            user_id=user_id,
            action="BUILD_BASELINE",
            entity_type="SourceBaseline",
            entity_id=baseline.id,
            details_json=json.dumps({
                "station_id": station_id,
                "status": baseline.status,
                "sample_count": sample_count,
                "version": baseline.version,
            }),
        )
        db.add(audit)
        db.commit()
        db.refresh(baseline)
        return baseline

    @classmethod
    def get_latest_baseline(cls, db: Session, station_id: int) -> Optional[SourceBaseline]:
        """Returns the most recent established or active baseline for a station."""
        return (
            db.query(SourceBaseline)
            .filter(
                SourceBaseline.station_id == station_id,
                SourceBaseline.status.in_(["established", "insufficient_data"]),
            )
            .order_by(SourceBaseline.id.desc())
            .first()
        )
