"""
AquaLens AI - Sources and Monitoring Stations API Endpoints
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db.models import WaterSource, MonitoringStation, Observation, User, SourceBaseline
from ..schemas.schemas import (
    WaterSourceCreate,
    WaterSourceOut,
    MonitoringStationCreate,
    MonitoringStationOut,
)
from .deps import get_current_user_optional, require_role

router = APIRouter(tags=["Sources & Stations"])


@router.get("/sources", response_model=List[WaterSourceOut])
def list_sources(
    region: Optional[str] = Query(None, description="Filter by geographic region"),
    source_type: Optional[str] = Query(None, description="Filter by water body type"),
    db: Session = Depends(get_db),
):
    query = db.query(WaterSource)
    if region:
        query = query.filter(WaterSource.region.ilike(f"%{region}%"))
    if source_type:
        query = query.filter(WaterSource.source_type.ilike(f"%{source_type}%"))
    return query.order_by(WaterSource.name.asc()).all()


@router.post("/sources", response_model=WaterSourceOut, status_code=status.HTTP_201_CREATED)
def create_source(
    source_in: WaterSourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "officer", "researcher")),
):
    existing = db.query(WaterSource).filter(WaterSource.source_code == source_in.source_code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Water source code '{source_in.source_code}' already exists.",
        )
    source = WaterSource(
        source_code=source_in.source_code,
        name=source_in.name,
        source_type=source_in.source_type,
        region=source_in.region,
        description=source_in.description,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("/stations", response_model=List[MonitoringStationOut])
def list_stations(
    source_id: Optional[int] = Query(None, description="Filter stations by source ID"),
    active_only: bool = Query(True, description="Filter active stations"),
    is_demo: Optional[bool] = Query(None, description="Filter by demo fixture status"),
    db: Session = Depends(get_db),
):
    query = db.query(MonitoringStation)
    if source_id:
        query = query.filter(MonitoringStation.source_id == source_id)
    if active_only:
        query = query.filter(MonitoringStation.active == True)
    if is_demo is not None:
        query = query.filter(MonitoringStation.is_demo == is_demo)
    
    stations = query.order_by(MonitoringStation.name.asc()).all()
    results = []
    for st in stations:
        # Populate latest observation metadata
        latest_obs = (
            db.query(Observation)
            .filter(Observation.station_id == st.id)
            .order_by(Observation.sampling_timestamp.desc())
            .first()
        )
        latest_time = latest_obs.sampling_timestamp if latest_obs else None
        latest_cond = latest_obs.classification.predicted_condition if (latest_obs and latest_obs.classification) else None
        health = latest_obs.health_score.score if (latest_obs and latest_obs.health_score and latest_obs.health_score.score is not None) else None
        anomaly_stat = latest_obs.anomaly_result.status if (latest_obs and latest_obs.anomaly_result) else None

        latest_bl = (
            db.query(SourceBaseline)
            .filter(SourceBaseline.station_id == st.id, SourceBaseline.status != "archived")
            .order_by(SourceBaseline.id.desc())
            .first()
        )
        baseline_stat = latest_bl.status if latest_bl else "insufficient_data"

        out = MonitoringStationOut(
            id=st.id,
            source_id=st.source_id,
            station_code=st.station_code,
            name=st.name,
            latitude=st.latitude,
            longitude=st.longitude,
            elevation_m=st.elevation_m,
            active=st.active,
            is_demo=st.is_demo,
            created_at=st.created_at,
            latest_observation_time=latest_time,
            latest_condition=latest_cond,
            baseline_status=baseline_stat,
            health_score=health,
            anomaly_status=anomaly_stat,
        )
        results.append(out)
    return results


@router.get("/stations/{id}", response_model=MonitoringStationOut)
def get_station(id: int, db: Session = Depends(get_db)):
    st = db.query(MonitoringStation).filter(MonitoringStation.id == id).first()
    if not st:
        raise HTTPException(status_code=404, detail=f"Monitoring station {id} not found.")

    latest_obs = (
        db.query(Observation)
        .filter(Observation.station_id == st.id)
        .order_by(Observation.sampling_timestamp.desc())
        .first()
    )
    latest_time = latest_obs.sampling_timestamp if latest_obs else None
    latest_cond = latest_obs.classification.predicted_condition if (latest_obs and latest_obs.classification) else None
    health = latest_obs.health_score.score if (latest_obs and latest_obs.health_score and latest_obs.health_score.score is not None) else None
    anomaly_stat = latest_obs.anomaly_result.status if (latest_obs and latest_obs.anomaly_result) else None

    latest_bl = (
        db.query(SourceBaseline)
        .filter(SourceBaseline.station_id == st.id, SourceBaseline.status != "archived")
        .order_by(SourceBaseline.id.desc())
        .first()
    )
    baseline_stat = latest_bl.status if latest_bl else "insufficient_data"

    return MonitoringStationOut(
        id=st.id,
        source_id=st.source_id,
        station_code=st.station_code,
        name=st.name,
        latitude=st.latitude,
        longitude=st.longitude,
        elevation_m=st.elevation_m,
        active=st.active,
        is_demo=st.is_demo,
        created_at=st.created_at,
        latest_observation_time=latest_time,
        latest_condition=latest_cond,
        baseline_status=baseline_stat,
        health_score=health,
        anomaly_status=anomaly_stat,
    )


@router.post("/stations", response_model=MonitoringStationOut, status_code=status.HTTP_201_CREATED)
def create_station(
    st_in: MonitoringStationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "officer", "researcher")),
):
    source = db.query(WaterSource).filter(WaterSource.id == st_in.source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Water source {st_in.source_id} not found.")
    existing = db.query(MonitoringStation).filter(MonitoringStation.station_code == st_in.station_code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Station code '{st_in.station_code}' already exists.")

    st = MonitoringStation(
        source_id=st_in.source_id,
        station_code=st_in.station_code,
        name=st_in.name,
        latitude=st_in.latitude,
        longitude=st_in.longitude,
        elevation_m=st_in.elevation_m,
        active=st_in.active,
        is_demo=st_in.is_demo,
    )
    db.add(st)
    db.commit()
    db.refresh(st)

    return MonitoringStationOut(
        id=st.id,
        source_id=st.source_id,
        station_code=st.station_code,
        name=st.name,
        latitude=st.latitude,
        longitude=st.longitude,
        elevation_m=st.elevation_m,
        active=st.active,
        is_demo=st.is_demo,
        created_at=st.created_at,
        baseline_status="insufficient_data",
    )
