"""
AquaLens AI - Water Health Score Service
Calculates a transparent, source-specific relative visual stability index.
Distinguishes mathematical method from validation status.
Never pretends to be a certified potability index or WQI.
"""

from typing import Dict, Any, Optional
import numpy as np
from sqlalchemy.orm import Session

from ..db.models import (
    Observation,
    SourceBaseline,
    AnomalyResult,
    WaterHealthScore,
)

METHODOLOGY_VERSION = "visual-relative-stability-v1.0"


class HealthScoreService:
    @classmethod
    def calculate_health_score(
        cls,
        db: Session,
        observation: Observation,
        anomaly_result: Optional[AnomalyResult] = None,
        baseline: Optional[SourceBaseline] = None,
    ) -> WaterHealthScore:
        """
        Calculates the relative visual stability score against the station baseline.
        If baseline is insufficient (< baseline threshold), returns score=None, status='unavailable'.
        """
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

        # Baseline check
        if not baseline or baseline.status != "established" or baseline.sample_count < 5:
            score_record = WaterHealthScore(
                observation_id=observation.id,
                baseline_id=baseline.id if baseline else None,
                score=None,
                status="unavailable",
                methodology_version=METHODOLOGY_VERSION,
                explanation="Water Health Score unavailable: insufficient validated baseline data.",
                limitations=(
                    "A source-specific visual baseline has not yet been established. "
                    "At least 5 validated reference observations are required before computing stability."
                ),
            )
            return score_record

        # Retrieve or compute anomaly score
        if anomaly_result is None:
            anomaly_result = observation.anomaly_result

        anomaly_score = (
            anomaly_result.overall_anomaly_score
            if (anomaly_result and anomaly_result.overall_anomaly_score is not None)
            else 0.0
        )

        # Calculate bounded relative visual stability score [0.0 - 100.0]
        # Formula: S = 100 * exp(-0.35 * anomaly_score)
        # When anomaly_score == 0 (identical to reference median), score = 100.
        # When anomaly_score == 2.5 (threshold), score ≈ 41.7.
        # When anomaly_score >= 5.0, score < 17.4.
        raw_score = 100.0 * float(np.exp(-0.35 * anomaly_score))
        bounded_score = round(float(np.clip(raw_score, 0.0, 100.0)), 1)

        # Validation status based on reference count and quality
        if baseline.sample_count >= 20:
            status = "validated"
        else:
            status = "provisional"

        explanation = (
            f"Visual condition is {bounded_score}/100 relative to Station "
            f"reference profile ({baseline.sample_count} observations in baseline {baseline.version})."
        )
        limitations = (
            "Relative visual condition score only. Does NOT establish potability, "
            "bacterial safety, chemical dissolved oxygen, or laboratory turbidity."
        )

        score_record = WaterHealthScore(
            observation_id=observation.id,
            baseline_id=baseline.id,
            score=bounded_score,
            status=status,
            methodology_version=METHODOLOGY_VERSION,
            explanation=explanation,
            limitations=limitations,
        )
        return score_record

    @classmethod
    def save_or_update_score(
        cls,
        db: Session,
        observation: Observation,
        anomaly_result: Optional[AnomalyResult] = None,
        baseline: Optional[SourceBaseline] = None,
    ) -> WaterHealthScore:
        score_record = cls.calculate_health_score(db, observation, anomaly_result, baseline)
        existing = db.query(WaterHealthScore).filter(WaterHealthScore.observation_id == observation.id).first()
        if existing:
            existing.baseline_id = score_record.baseline_id
            existing.score = score_record.score
            existing.status = score_record.status
            existing.methodology_version = score_record.methodology_version
            existing.explanation = score_record.explanation
            existing.limitations = score_record.limitations
            db.commit()
            db.refresh(existing)
            return existing
        else:
            db.add(score_record)
            db.commit()
            db.refresh(score_record)
            return score_record
