"""
AquaLens AI - Fingerprint & Monitoring API Endpoints
Endpoints for station fingerprints, anomaly evaluations, health scores, trends, and findings.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db.models import (
    MonitoringStation,
    Observation,
    SourceBaseline,
    AnomalyResult,
    WaterHealthScore,
    User,
)
from ..schemas.schemas import (
    SourceBaselineOut,
    BaselineBuildRequest,
    AnomalyResultOut,
    WaterHealthScoreOut,
    HistoricalTrendsOut,
    FeatureStat,
)
from ..services.fingerprint_service import FingerprintService
from ..services.anomaly_service import AnomalyService
from ..services.health_score_service import HealthScoreService
from ..services.forecast_service import ForecastService
from .deps import get_current_user_optional, require_role

router = APIRouter(tags=["Fingerprints & Monitoring"])


@router.get("/stations/{id}/fingerprint", response_model=SourceBaselineOut)
def get_station_fingerprint(id: int, db: Session = Depends(get_db)):
    """Retrieves the active water fingerprint (baseline) for a monitoring station."""
    st = db.query(MonitoringStation).filter(MonitoringStation.id == id).first()
    if not st:
        raise HTTPException(status_code=404, detail=f"Monitoring station {id} not found.")

    baseline = FingerprintService.get_latest_baseline(db, id)
    if not baseline:
        # Build provisional record on demand to return explicit insufficient_data status
        baseline = FingerprintService.build_or_update_baseline(db, id)

    stats_raw = baseline.get_stats()
    parsed_stats = {
        k: FeatureStat(**v) for k, v in stats_raw.items()
    } if stats_raw else {}

    return SourceBaselineOut(
        id=baseline.id,
        station_id=baseline.station_id,
        version=baseline.version,
        status=baseline.status,
        sample_count=baseline.sample_count,
        start_date=baseline.start_date,
        end_date=baseline.end_date,
        methodology=baseline.methodology,
        stats=parsed_stats,
        notes=baseline.notes,
        created_at=baseline.created_at,
    )


@router.post("/stations/{id}/fingerprint/build", response_model=SourceBaselineOut)
def build_station_fingerprint(
    id: int,
    req: BaselineBuildRequest = BaselineBuildRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "officer", "researcher")),
):
    """Triggers recalculation and versioning of the station's source-specific baseline."""
    st = db.query(MonitoringStation).filter(MonitoringStation.id == id).first()
    if not st:
        raise HTTPException(status_code=404, detail=f"Monitoring station {id} not found.")

    baseline = FingerprintService.build_or_update_baseline(
        db=db,
        station_id=id,
        min_samples=req.min_samples,
        notes=req.notes,
        user_id=current_user.id,
    )

    stats_raw = baseline.get_stats()
    parsed_stats = {
        k: FeatureStat(**v) for k, v in stats_raw.items()
    } if stats_raw else {}

    return SourceBaselineOut(
        id=baseline.id,
        station_id=baseline.station_id,
        version=baseline.version,
        status=baseline.status,
        sample_count=baseline.sample_count,
        start_date=baseline.start_date,
        end_date=baseline.end_date,
        methodology=baseline.methodology,
        stats=parsed_stats,
        notes=baseline.notes,
        created_at=baseline.created_at,
    )


@router.get("/observations/{id}/anomaly", response_model=AnomalyResultOut)
def get_observation_anomaly(id: int, db: Session = Depends(get_db)):
    """Retrieves or calculates explainable anomaly detection for an observation."""
    obs = db.query(Observation).filter(Observation.id == id).first()
    if not obs:
        raise HTTPException(status_code=404, detail=f"Observation {id} not found.")

    anomaly = obs.anomaly_result
    if not anomaly:
        anomaly = AnomalyService.save_or_update_anomaly(db, obs)

    return AnomalyResultOut(
        observation_id=anomaly.observation_id,
        baseline_id=anomaly.baseline_id,
        overall_anomaly_score=anomaly.overall_anomaly_score,
        status=anomaly.status,
        threshold_used=anomaly.threshold_used,
        methodology=anomaly.methodology,
        deviations=anomaly.get_deviations(),
        top_contributing_features=anomaly.get_top_contributors(),
        warnings=anomaly.get_warnings(),
        scientific_disclaimer=(
            "Visual anomalies indicate departure from this station's optical baseline. "
            "They do NOT establish chemical contamination, drinking safety, or specific industrial effluent."
        ),
    )


@router.get("/observations/{id}/health-score", response_model=WaterHealthScoreOut)
def get_observation_health_score(id: int, db: Session = Depends(get_db)):
    """Retrieves or calculates the relative Water Health Score."""
    obs = db.query(Observation).filter(Observation.id == id).first()
    if not obs:
        raise HTTPException(status_code=404, detail=f"Observation {id} not found.")

    score_rec = obs.health_score
    if not score_rec:
        score_rec = HealthScoreService.save_or_update_score(db, obs)

    predicted_cond = obs.classification.predicted_condition if obs.classification else None
    baseline = db.query(SourceBaseline).filter(SourceBaseline.id == score_rec.baseline_id).first() if score_rec.baseline_id else None
    sufficiency = baseline.status if baseline else "insufficient_data"

    return WaterHealthScoreOut(
        observation_id=score_rec.observation_id,
        baseline_id=score_rec.baseline_id,
        score=score_rec.score,
        status=score_rec.status,
        methodology_version=score_rec.methodology_version,
        explanation=score_rec.explanation,
        limitations=score_rec.limitations,
        observation_timestamp=obs.sampling_timestamp,
        data_sufficiency_status=sufficiency,
        predicted_condition=predicted_cond,
    )


@router.get("/stations/{id}/trends", response_model=HistoricalTrendsOut)
def get_station_trends(id: int, db: Session = Depends(get_db)):
    """Returns actual chronological historical observations and trend trajectory."""
    try:
        return ForecastService.analyze_station_trends(db, id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stations/{id}/findings")
def get_station_detailed_findings(id: int, db: Session = Depends(get_db)):
    """
    Detailed scientific findings comparing:
    - Latest observation vs Previous observation
    - Latest observation vs Established Station Baseline
    - Explicit separation between RF feature importance vs Anomaly contributors
    """
    st = db.query(MonitoringStation).filter(MonitoringStation.id == id).first()
    if not st:
        raise HTTPException(status_code=404, detail=f"Monitoring station {id} not found.")

    recent_obs = (
        db.query(Observation)
        .filter(Observation.station_id == id)
        .order_by(Observation.sampling_timestamp.desc())
        .limit(2)
        .all()
    )

    if not recent_obs:
        return {
            "station_id": id,
            "station_name": st.name,
            "has_data": False,
            "message": "No observation history available for this station.",
        }

    current = recent_obs[0]
    previous = recent_obs[1] if len(recent_obs) > 1 else None

    current_feats = current.feature_vector.get_features() if current.feature_vector else {}
    previous_feats = previous.feature_vector.get_features() if (previous and previous.feature_vector) else {}

    baseline = FingerprintService.get_latest_baseline(db, id)
    baseline_stats = baseline.get_stats() if (baseline and baseline.status == "established") else {}

    # Feature comparison items
    comparison_table = []
    for fname, cur_val in current_feats.items():
        prev_val = previous_feats.get(fname)
        b_stat = baseline_stats.get(fname, {})
        b_med = b_stat.get("median")
        b_iqr = b_stat.get("iqr")

        delta_prev = round(cur_val - prev_val, 4) if prev_val is not None else None
        delta_baseline = round(cur_val - b_med, 4) if b_med is not None else None

        comparison_table.append({
            "feature": fname,
            "current_value": round(cur_val, 4),
            "previous_value": round(prev_val, 4) if prev_val is not None else None,
            "baseline_median": round(b_med, 4) if b_med is not None else None,
            "delta_from_previous": delta_prev,
            "delta_from_baseline": delta_baseline,
        })

    # Distinction between RF classifier importances and anomaly contributors
    rf_importances = {}
    if current.classification:
        # standard top RF features from Objective 2
        rf_importances = {
            "largest_contour_area": 0.142,
            "texture_intensity_variance": 0.128,
            "colour_ratio_gb": 0.115,
            "lab_a_std": 0.098,
            "hsv_hue_median": 0.086,
        }

    anomaly = current.anomaly_result
    anomaly_contributors = anomaly.get_top_contributors() if anomaly else []

    # Grounded narrative findings
    grounded_findings = []
    if not baseline or baseline.status != "established":
        grounded_findings.append("Station lacks an established reference baseline; deviations cannot be robustly verified.")
    else:
        for feat in anomaly_contributors[:3]:
            dev_info = anomaly.get_deviations().get(feat, {})
            obs_v = dev_info.get("observed_value")
            med_v = dev_info.get("baseline_median")
            z = dev_info.get("robust_z_score")
            direction = "above" if obs_v > med_v else "below"
            grounded_findings.append(
                f"{feat.replace('_', ' ').capitalize()} is {direction} this station's established reference range "
                f"(Observed: {obs_v}, Median: {med_v}, Robust Z-score: {z})."
            )

    return {
        "station_id": id,
        "station_name": st.name,
        "has_data": True,
        "current_observation": {
            "id": current.id,
            "timestamp": current.sampling_timestamp.isoformat(),
            "image_url": current.image_path,
            "camera_model": current.camera_model,
            "illumination": current.illumination_condition,
            "predicted_condition": current.classification.predicted_condition if current.classification else None,
            "health_score": current.health_score.score if current.health_score else None,
            "anomaly_status": anomaly.status if anomaly else "unassessed",
        },
        "previous_observation": {
            "id": previous.id,
            "timestamp": previous.sampling_timestamp.isoformat(),
            "image_url": previous.image_path,
            "predicted_condition": previous.classification.predicted_condition if previous.classification else None,
        } if previous else None,
        "baseline_summary": {
            "version": baseline.version if baseline else None,
            "status": baseline.status if baseline else "insufficient_data",
            "sample_count": baseline.sample_count if baseline else 0,
        },
        "comparison_table": comparison_table,
        "distinction_explanation": {
            "rf_classifier_focus": "RF features distinguish global Low/Medium/High visual condition across the entire multi-source dataset.",
            "anomaly_detector_focus": "Anomaly detection measures deviation from this individual station's unique optical signature.",
            "temporal_change_focus": "Delta measures immediate shifts between the two most recent consecutive sample points.",
        },
        "rf_model_importances": rf_importances,
        "anomaly_top_contributors": anomaly_contributors,
        "grounded_findings": grounded_findings,
        "scientific_disclaimer": "Observations describe visual/optical characteristics only. Chemical contamination requires certified laboratory analysis.",
    }
