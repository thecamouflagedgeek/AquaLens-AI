"""Location-driven satellite monitoring API.

Mounted twice by ``backend/app/main.py`` (under ``/api/v1`` and at the root), matching the
convention used by the auth/sources/observations/monitoring/advanced routers.

Every route requires an authenticated session (``get_current_user``). Earth Engine
failures are reported explicitly: ``503`` when the integration is not usable and ``502``
when a query fails. Nothing here fabricates data when Earth Engine is unavailable.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.models import User
from ..db.session import get_db
from ..satellite import aoi as aoi_module
from ..satellite import gee, indices, service
from ..satellite.models import SatelliteAOI
from ..satellite.schemas import AoiResolveRequest, SatelliteFetchRequest
from .deps import get_current_user

router = APIRouter(
    prefix="/satellite",
    tags=["Satellite monitoring"],
    dependencies=[Depends(get_current_user)],
)


def _require_aoi(db: Session, aoi_id: int) -> SatelliteAOI:
    row = db.get(SatelliteAOI, aoi_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Satellite area of interest {aoi_id} not found.")
    return row


def _defaults() -> Dict[str, Any]:
    return {
        "collection": settings.SATELLITE_COLLECTION,
        "algorithm": indices.ALGORITHM,
        "algorithm_version": indices.ALGORITHM_VERSION,
        "ndwi_threshold": indices.NDWI_THRESHOLD_DEFAULT,
        "max_cloud_pct": indices.MAX_CLOUD_PCT_DEFAULT,
        "default_buffer_m": aoi_module.DEFAULT_BUFFER_M,
        "default_months": settings.SATELLITE_DEFAULT_MONTHS,
        "native_pixel_size_m": indices.NATIVE_PIXEL_SIZE_M,
        "method": indices.describe_method(),
    }


@router.get("/status")
def satellite_status():
    """Readiness report for the Earth Engine integration. Contains no secret values."""
    return {"earth_engine": gee.status(), "defaults": _defaults()}


@router.post("/aois/resolve", status_code=status.HTTP_200_OK)
def resolve_aoi(body: AoiResolveRequest, db: Session = Depends(get_db)):
    """Create or resolve a reusable area of interest.

    A point is expanded by ``buffer_m`` (default 300 m) into a circular polygon; a
    GeoJSON polygon is validated as supplied. Repeating the same request returns the same
    stored AOI, so a location's history is reused across sessions.
    """
    try:
        row, created = service.get_or_create_aoi(
            db,
            name=body.name,
            latitude=body.latitude,
            longitude=body.longitude,
            buffer_m=body.buffer_m,
            geometry=body.geometry,
            station_ref=body.station_ref,
            country=body.country,
            notes=body.notes,
        )
    except aoi_module.AOIValidationError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {"aoi": service.aoi_payload(row), "created": created}


@router.get("/aois")
def list_aois(
    station_ref: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(SatelliteAOI)
    if station_ref:
        query = query.filter(SatelliteAOI.station_ref == station_ref)
    rows = query.order_by(SatelliteAOI.updated_at.desc()).limit(limit).all()
    return {"items": [service.aoi_payload(row) for row in rows], "total": len(rows)}


@router.get("/aois/{aoi_id}")
def get_aoi(aoi_id: int, db: Session = Depends(get_db)):
    return {"aoi": service.aoi_payload(_require_aoi(db, aoi_id)), "defaults": _defaults()}


@router.get("/aois/{aoi_id}/observations")
def get_observations(
    aoi_id: int,
    start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    end_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    ndwi_threshold: Optional[float] = Query(default=None, ge=-1.0, le=1.0),
    max_cloud_pct: Optional[int] = Query(default=None, ge=0, le=100),
    db: Session = Depends(get_db),
):
    """Return persisted monthly observations for an AOI.

    Months that were fetched but had no usable imagery are included with
    ``status='no_scenes'``/``'no_valid_pixels'`` and null measurements. Months never
    fetched are reported by the availability block rather than invented here.
    """
    row = _require_aoi(db, aoi_id)
    threshold = indices.NDWI_THRESHOLD_DEFAULT if ndwi_threshold is None else float(ndwi_threshold)
    cloud = indices.MAX_CLOUD_PCT_DEFAULT if max_cloud_pct is None else int(max_cloud_pct)

    rows = service.list_observations(
        db,
        aoi_id,
        start_month=start_month,
        end_month=end_month,
        collection=settings.SATELLITE_COLLECTION,
        algorithm_version=indices.ALGORITHM_VERSION,
        ndwi_threshold=threshold,
        max_cloud_pct=cloud,
    )

    if start_month and end_month:
        availability = service.availability(
            db,
            aoi_id,
            start_month=start_month,
            end_month=end_month,
            collection=settings.SATELLITE_COLLECTION,
            algorithm_version=indices.ALGORITHM_VERSION,
            ndwi_threshold=threshold,
            max_cloud_pct=cloud,
        )
    else:
        availability = None

    return {
        "aoi": service.aoi_payload(row),
        "items": [service.observation_payload(item) for item in rows],
        "total": len(rows),
        "availability": availability,
        "ndwi_threshold": threshold,
        "max_cloud_pct": cloud,
        "algorithm": indices.ALGORITHM,
        "algorithm_version": indices.ALGORITHM_VERSION,
        "collection": settings.SATELLITE_COLLECTION,
        "measured": "satellite-derived surface-water indicator (NDWI)",
        "caveat": (
            "NDWI is a spectral water indicator, not a measurement of dissolved oxygen, BOD, "
            "turbidity or chemical contamination. Water area from an NDWI threshold is an "
            "estimate, not surveyed ground truth."
        ),
    }


@router.get("/aois/{aoi_id}/availability")
def get_availability(
    aoi_id: int,
    start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    end_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    months: Optional[int] = Query(default=None, ge=1, le=240),
    ndwi_threshold: Optional[float] = Query(default=None, ge=-1.0, le=1.0),
    max_cloud_pct: Optional[int] = Query(default=None, ge=0, le=100),
    db: Session = Depends(get_db),
):
    """Coverage and data-availability report for a window, without fetching anything."""
    _require_aoi(db, aoi_id)
    threshold = indices.NDWI_THRESHOLD_DEFAULT if ndwi_threshold is None else float(ndwi_threshold)
    cloud = indices.MAX_CLOUD_PCT_DEFAULT if max_cloud_pct is None else int(max_cloud_pct)

    if not start_month or not end_month:
        start_month, end_month = indices.default_window(months or settings.SATELLITE_DEFAULT_MONTHS)

    return service.availability(
        db,
        aoi_id,
        start_month=start_month,
        end_month=end_month,
        collection=settings.SATELLITE_COLLECTION,
        algorithm_version=indices.ALGORITHM_VERSION,
        ndwi_threshold=threshold,
        max_cloud_pct=cloud,
    )


@router.post("/aois/{aoi_id}/fetch", status_code=status.HTTP_202_ACCEPTED)
def start_fetch(aoi_id: int, body: SatelliteFetchRequest, db: Session = Depends(get_db)):
    """Queue retrieval of missing months for an AOI.

    Long historical computation is never performed inside this request: the job is
    persisted and processed in the background. Earth Engine configuration/auth problems
    are surfaced immediately as ``503`` so the dashboard can show an actionable error.
    """
    row = _require_aoi(db, aoi_id)

    try:
        gee.ensure_ready()
    except gee.GeeUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error))
    except gee.GeeError as error:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail=str(error))

    try:
        job = service.start_fetch(
            db,
            row,
            start_month=body.start_month,
            end_month=body.end_month,
            months=body.months,
            ndwi_threshold=body.ndwi_threshold,
            max_cloud_pct=body.max_cloud_pct,
            force=body.force,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    reused = bool(getattr(job, "reused_active_job", False))
    if reused:
        message = (
            "A retrieval for this area and period is already in progress; "
            "continuing to track that job."
        )
    elif job.status == "completed" and not job.months_total:
        message = "All requested months were already stored; nothing to fetch."
    else:
        message = "Satellite history retrieval started in the background."

    return {
        "job": service.job_status(db, job.id),
        "aoi": service.aoi_payload(row),
        "reused": reused,
        "message": message,
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    """Poll acquisition/processing status for a fetch job."""
    try:
        return service.job_status(db, job_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
