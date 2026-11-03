"""
AquaLens AI - Advanced Analysis API Endpoints
Handles time-series forecasting, evidence-based recommendations, and laboratory verification records.
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db.models import (
    MonitoringStation,
    Observation,
    LaboratoryResult,
    Recommendation,
    User,
)
from ..schemas.schemas import (
    ForecastOut,
    RecommendationOut,
    LaboratoryResultOut,
)
from ..services.forecast_service import ForecastService
from ..services.recommendation_service import RecommendationService
from .deps import get_current_user_optional, require_role

router = APIRouter(tags=["Advanced Analysis"])


class LabResultCreate(BaseModel):
    sample_timestamp: Optional[datetime] = None
    turbidity_ntu: Optional[float] = None
    ph: Optional[float] = None
    dissolved_oxygen_mg_l: Optional[float] = None
    tss_mg_l: Optional[float] = None
    conductivity_us_cm: Optional[float] = None
    lab_operator: Optional[str] = None
    notes: Optional[str] = None


@router.get("/stations/{id}/forecast", response_model=ForecastOut)
def get_station_forecast(
    id: int,
    horizon_days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """
    Returns time-series forecast for the station if sufficient chronological history exists.
    Returns status='insufficient_data' if fewer than 10 observations with validated health scores exist.
    """
    try:
        return ForecastService.generate_station_forecast(db, id, horizon_days=horizon_days)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stations/{id}/recommendations", response_model=List[RecommendationOut])
def get_station_recommendations(id: int, db: Session = Depends(get_db)):
    """Retrieves deterministic, evidence-based recommendations for the station's latest condition."""
    st = db.query(MonitoringStation).filter(MonitoringStation.id == id).first()
    if not st:
        raise HTTPException(status_code=404, detail=f"Monitoring station {id} not found.")

    latest_obs = (
        db.query(Observation)
        .filter(Observation.station_id == id)
        .order_by(Observation.sampling_timestamp.desc())
        .first()
    )

    if not latest_obs:
        return []

    recs = (
        db.query(Recommendation)
        .filter(Recommendation.observation_id == latest_obs.id)
        .all()
    )

    if not recs:
        recs = RecommendationService.sync_recommendations(db, latest_obs)

    return [
        RecommendationOut(
            id=r.id,
            station_id=r.station_id,
            observation_id=r.observation_id,
            category=r.category,
            title=r.title,
            description=r.description,
            hypothesis=r.hypothesis,
            action_items=r.get_action_items(),
            priority=r.priority,
            created_at=r.created_at,
        )
        for r in recs
    ]


@router.get("/stations/{id}/laboratory-results", response_model=List[LaboratoryResultOut])
def list_station_laboratory_results(id: int, db: Session = Depends(get_db)):
    """Returns actual laboratory measurements (kept strictly distinct from image estimations)."""
    st = db.query(MonitoringStation).filter(MonitoringStation.id == id).first()
    if not st:
        raise HTTPException(status_code=404, detail=f"Monitoring station {id} not found.")

    lab_records = (
        db.query(LaboratoryResult)
        .filter(LaboratoryResult.station_id == id)
        .order_by(LaboratoryResult.sample_timestamp.desc())
        .all()
    )
    return lab_records


@router.post("/stations/{id}/laboratory-results", response_model=LaboratoryResultOut, status_code=status.HTTP_201_CREATED)
def add_laboratory_result(
    id: int,
    result_in: LabResultCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "officer", "researcher")),
):
    """Registers certified laboratory analytical test results for validation."""
    st = db.query(MonitoringStation).filter(MonitoringStation.id == id).first()
    if not st:
        raise HTTPException(status_code=404, detail=f"Monitoring station {id} not found.")

    record = LaboratoryResult(
        station_id=id,
        sample_timestamp=result_in.sample_timestamp or datetime.now(timezone.utc),
        turbidity_ntu=result_in.turbidity_ntu,
        ph=result_in.ph,
        dissolved_oxygen_mg_l=result_in.dissolved_oxygen_mg_l,
        tss_mg_l=result_in.tss_mg_l,
        conductivity_us_cm=result_in.conductivity_us_cm,
        lab_operator=result_in.lab_operator,
        notes=result_in.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
