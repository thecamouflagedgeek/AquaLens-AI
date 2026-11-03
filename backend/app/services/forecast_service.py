"""
AquaLens AI - Time-Series Forecasting & Trend Analysis Service
Enforces scientific honesty: returns 'insufficient_data' unless enough temporal
observations exist to support chronological validation.
"""

from datetime import datetime, timedelta, timezone
import json
from typing import Dict, Any, List, Optional
import numpy as np
from sqlalchemy.orm import Session

from ..db.models import (
    MonitoringStation,
    Observation,
    WaterHealthScore,
    AnomalyResult,
    ForecastRun,
)

MIN_FORECAST_OBSERVATIONS = 10


class ForecastService:
    @classmethod
    def analyze_station_trends(cls, db: Session, station_id: int) -> Dict[str, Any]:
        """
        Retrieves real historical observations and trends for the station.
        No fabricated datapoints.
        """
        station = db.query(MonitoringStation).filter(MonitoringStation.id == station_id).first()
        if not station:
            raise ValueError(f"Station {station_id} not found.")

        observations = (
            db.query(Observation)
            .filter(Observation.station_id == station_id)
            .order_by(Observation.sampling_timestamp.asc())
            .all()
        )

        points = []
        for obs in observations:
            classification_condition = (
                obs.classification.predicted_condition if obs.classification else "Unclassified"
            )
            health = obs.health_score.score if (obs.health_score and obs.health_score.score is not None) else None
            anomaly = (
                obs.anomaly_result.overall_anomaly_score
                if (obs.anomaly_result and obs.anomaly_result.overall_anomaly_score is not None)
                else None
            )

            feats = obs.feature_vector.get_features() if obs.feature_vector else {}

            points.append({
                "observation_id": obs.id,
                "timestamp": obs.sampling_timestamp.isoformat(),
                "predicted_condition": classification_condition,
                "health_score": health,
                "anomaly_score": anomaly,
                "texture_intensity_variance": feats.get("texture_intensity_variance"),
                "colour_cast_blue_red": feats.get("colour_cast_blue_red"),
                "largest_contour_area": feats.get("largest_contour_area"),
            })

        summary = (
            f"Retrieved {len(points)} real historical observation(s) from Station {station.name}."
            if points
            else "No observations recorded for this station."
        )

        return {
            "station_id": station.id,
            "station_name": station.name,
            "total_observations": len(points),
            "time_range_start": points[0]["timestamp"] if points else None,
            "time_range_end": points[-1]["timestamp"] if points else None,
            "points": points,
            "summary": summary,
        }

    @classmethod
    def generate_station_forecast(
        cls,
        db: Session,
        station_id: int,
        horizon_days: int = 7,
    ) -> Dict[str, Any]:
        """
        Evaluates sufficiency. If observations < MIN_FORECAST_OBSERVATIONS, returns
        status='insufficient_data' with explanation:
        'Insufficient historical observations for a reliable forecast.'
        """
        station = db.query(MonitoringStation).filter(MonitoringStation.id == station_id).first()
        if not station:
            raise ValueError(f"Station {station_id} not found.")

        # Query observations with health scores
        observations = (
            db.query(Observation)
            .join(WaterHealthScore, WaterHealthScore.observation_id == Observation.id)
            .filter(
                Observation.station_id == station_id,
                WaterHealthScore.score.isnot(None),
            )
            .order_by(Observation.sampling_timestamp.asc())
            .all()
        )

        sample_count = len(observations)
        if sample_count < MIN_FORECAST_OBSERVATIONS:
            return {
                "station_id": station_id,
                "status": "insufficient_data",
                "method": "exponential-smoothing-trend",
                "horizon_days": horizon_days,
                "forecast_points": [],
                "validation_metrics": {},
                "explanation": (
                    f"Insufficient historical observations for a reliable forecast. "
                    f"Requires at least {MIN_FORECAST_OBSERVATIONS} chronological records with validated health scores; "
                    f"currently only {sample_count} available."
                ),
            }

        # If sufficient data: Simple Exponential Smoothing with trend (Holt's linear)
        scores = [float(obs.health_score.score) for obs in observations]
        dates = [obs.sampling_timestamp for obs in observations]

        # Chronological train-validation split (last 20% for validation)
        split_idx = max(int(len(scores) * 0.8), len(scores) - 3)
        train_scores = scores[:split_idx]
        val_scores = scores[split_idx:]

        # Simple linear trend on training set
        x_train = np.arange(len(train_scores))
        coeffs = np.polyfit(x_train, train_scores, 1)
        slope, intercept = coeffs[0], coeffs[1]

        # Validation evaluation
        x_val = np.arange(len(train_scores), len(scores))
        val_preds = slope * x_val + intercept
        mae = float(round(float(np.mean(np.abs(val_preds - val_scores))), 2))
        std_resid = float(round(float(np.std(train_scores - (slope * x_train + intercept))), 2))

        # Project future points
        last_date = dates[-1]
        forecast_points = []
        for day in range(1, horizon_days + 1):
            future_date = (last_date + timedelta(days=day)).strftime("%Y-%m-%d")
            pred_x = len(scores) + day - 1
            pred_score = float(np.clip(slope * pred_x + intercept, 0.0, 100.0))
            forecast_points.append({
                "date": future_date,
                "predicted_health_score": round(pred_score, 1),
                "uncertainty_lower": round(float(np.clip(pred_score - 1.96 * std_resid, 0.0, 100.0)), 1),
                "uncertainty_upper": round(float(np.clip(pred_score + 1.96 * std_resid, 0.0, 100.0)), 1),
            })

        return {
            "station_id": station_id,
            "status": "completed",
            "method": "chronologically-validated-linear-trend",
            "horizon_days": horizon_days,
            "forecast_points": forecast_points,
            "validation_metrics": {
                "validation_mae": mae,
                "residual_std": std_resid,
                "validation_samples": len(val_scores),
            },
            "explanation": (
                f"Trend computed using chronological validation on {sample_count} observations. "
                "Prediction intervals indicate 95% uncertainty margin based on empirical residual variance."
            ),
        }
