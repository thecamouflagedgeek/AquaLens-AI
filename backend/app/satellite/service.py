"""Orchestration and persistence for satellite retrieval.

Responsibilities:

- resolve/update an AOI row (idempotent by ``aoi_key``)
- decide which months still need fetching (incremental, resumable)
- run the fetch off the request thread and persist job progress
- upsert monthly observations so re-running never duplicates rows

No camera-pipeline module is imported here.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.session import SessionLocal
from . import aoi as aoi_module
from . import gee, indices
from .models import SatelliteAOI, SatelliteFetchJob, SatelliteObservation

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
# A job whose worker thread disappeared (e.g. the backend process was restarted while it was
# queued or running). It is terminal, keeps its progress counters, and can be retried by
# posting the fetch again -- retries stay incremental because stored months are skipped.
STATUS_INTERRUPTED = "interrupted"

ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)
TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_FAILED, STATUS_INTERRUPTED)

# Job ids with a live worker in *this* process. Startup recovery must never mark these
# interrupted; nothing else may assume a job row with an active status still has a worker.
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_JOB_IDS: set = set()


def _register_active(job_id: int) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_JOB_IDS.add(job_id)


def _unregister_active(job_id: int) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_JOB_IDS.discard(job_id)


def active_job_ids() -> set:
    """Job ids currently owned by a worker in this process (test/diagnostic helper)."""
    with _ACTIVE_LOCK:
        return set(_ACTIVE_JOB_IDS)


# --------------------------------------------------------------------------- AOI


def get_or_create_aoi(
    db: Session,
    *,
    name: Optional[str] = None,
    latitude: Any = None,
    longitude: Any = None,
    buffer_m: Any = None,
    geometry: Any = None,
    station_ref: Optional[str] = None,
    country: Optional[str] = None,
    notes: Optional[str] = None,
) -> Tuple[SatelliteAOI, bool]:
    """Resolve input into a persisted AOI. Returns ``(row, created)``.

    The same geometry always maps to the same row, so revisiting a location in a later
    session reuses its stored observations instead of creating a duplicate area.
    """
    spec = aoi_module.build_aoi(
        name=name,
        latitude=latitude,
        longitude=longitude,
        buffer_m=buffer_m,
        geometry=geometry,
        station_ref=station_ref,
    )

    existing = db.query(SatelliteAOI).filter(SatelliteAOI.aoi_key == spec["aoi_key"]).first()
    if existing is not None:
        changed = False
        if spec["name"] and spec["name"] != "Unnamed area of interest" and existing.name != spec["name"]:
            existing.name = spec["name"]
            changed = True
        if station_ref and existing.station_ref != station_ref:
            existing.station_ref = station_ref
            changed = True
        if country and existing.country != country:
            existing.country = country
            changed = True
        if notes and existing.notes != notes:
            existing.notes = notes
            changed = True
        if changed:
            db.commit()
            db.refresh(existing)
        return existing, False

    row = SatelliteAOI(
        aoi_key=spec["aoi_key"],
        name=spec["name"],
        kind=spec["kind"],
        latitude=spec["latitude"],
        longitude=spec["longitude"],
        buffer_m=spec["buffer_m"],
        geometry_geojson=json.dumps(spec["geometry"], allow_nan=False),
        area_km2=spec["area_km2"],
        station_ref=spec["station_ref"],
        country=country,
        notes=notes,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Another worker inserted the same AOI between the SELECT and the INSERT.
        db.rollback()
        row = db.query(SatelliteAOI).filter(SatelliteAOI.aoi_key == spec["aoi_key"]).one()
        return row, False
    db.refresh(row)
    return row, True


def aoi_geometry(row: SatelliteAOI) -> Dict[str, Any]:
    return json.loads(row.geometry_geojson)


def aoi_payload(row: SatelliteAOI) -> Dict[str, Any]:
    return {
        "id": row.id,
        "aoi_key": row.aoi_key,
        "name": row.name,
        "kind": row.kind,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "buffer_m": row.buffer_m,
        "area_km2": row.area_km2,
        "station_ref": row.station_ref,
        "country": row.country,
        "notes": row.notes,
        "geometry": json.loads(row.geometry_geojson),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ------------------------------------------------------------------ observations


def identity_filter(
    aoi_id: int,
    *,
    collection: str,
    algorithm_version: str,
    ndwi_threshold: float,
    max_cloud_pct: int,
):
    return (
        SatelliteObservation.aoi_id == aoi_id,
        SatelliteObservation.collection == collection,
        SatelliteObservation.algorithm_version == algorithm_version,
        SatelliteObservation.ndwi_threshold == float(ndwi_threshold),
        SatelliteObservation.max_cloud_pct == int(max_cloud_pct),
    )


def stored_months(
    db: Session,
    aoi_id: int,
    *,
    collection: str,
    algorithm_version: str,
    ndwi_threshold: float,
    max_cloud_pct: int,
) -> set:
    rows = (
        db.query(SatelliteObservation.month)
        .filter(
            *identity_filter(
                aoi_id,
                collection=collection,
                algorithm_version=algorithm_version,
                ndwi_threshold=ndwi_threshold,
                max_cloud_pct=max_cloud_pct,
            )
        )
        .all()
    )
    return {row[0] for row in rows}


def observation_payload(row: SatelliteObservation) -> Dict[str, Any]:
    return {
        "id": row.id,
        "aoi_id": row.aoi_id,
        "month": row.month,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "collection": row.collection,
        "sensor": row.sensor,
        "resolution_m": row.resolution_m,
        "ndwi_mean": row.ndwi_mean,
        "ndwi_median": row.ndwi_median,
        "water_area_km2": row.water_area_km2,
        "water_fraction": row.water_fraction,
        "scene_count": row.scene_count,
        "valid_pixel_count": row.valid_pixel_count,
        "ndwi_threshold": row.ndwi_threshold,
        "max_cloud_pct": row.max_cloud_pct,
        "status": row.status,
        "algorithm": row.algorithm,
        "algorithm_version": row.algorithm_version,
        "mask_rule": row.mask_rule,
        "quality": json.loads(row.quality_json) if row.quality_json else None,
        "notes": row.notes,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
    }


def list_observations(
    db: Session,
    aoi_id: int,
    *,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    collection: str,
    algorithm_version: str,
    ndwi_threshold: float,
    max_cloud_pct: int,
) -> List[SatelliteObservation]:
    query = db.query(SatelliteObservation).filter(
        *identity_filter(
            aoi_id,
            collection=collection,
            algorithm_version=algorithm_version,
            ndwi_threshold=ndwi_threshold,
            max_cloud_pct=max_cloud_pct,
        )
    )
    if start_month:
        query = query.filter(SatelliteObservation.month >= start_month)
    if end_month:
        query = query.filter(SatelliteObservation.month <= end_month)
    return query.order_by(SatelliteObservation.month.asc()).all()


def availability(
    db: Session,
    aoi_id: int,
    *,
    start_month: str,
    end_month: str,
    collection: str,
    algorithm_version: str,
    ndwi_threshold: float,
    max_cloud_pct: int,
) -> Dict[str, Any]:
    """Coverage report: which months are stored, usable, or absent."""
    months = indices.month_sequence(start_month, end_month)
    rows = {
        row.month: row
        for row in list_observations(
            db,
            aoi_id,
            start_month=start_month,
            end_month=end_month,
            collection=collection,
            algorithm_version=algorithm_version,
            ndwi_threshold=ndwi_threshold,
            max_cloud_pct=max_cloud_pct,
        )
    }

    with_data, without_data, not_fetched = [], [], []
    for month in months:
        row = rows.get(month)
        if row is None:
            not_fetched.append(month)
        elif row.status == indices.STATUS_OK:
            with_data.append(month)
        else:
            without_data.append({"month": month, "reason": row.status})

    return {
        "start_month": start_month,
        "end_month": end_month,
        "months_expected": len(months),
        "months_with_data": len(with_data),
        "months_recorded_without_data": len(without_data),
        "months_not_fetched": len(not_fetched),
        "with_data": with_data,
        "without_data": without_data,
        "not_fetched": not_fetched,
        "is_complete": not not_fetched,
        "ndwi_threshold": float(ndwi_threshold),
        "max_cloud_pct": int(max_cloud_pct),
        "algorithm": indices.ALGORITHM,
        "algorithm_version": algorithm_version,
    }


def _upsert_observation(
    db: Session,
    row_aoi: SatelliteAOI,
    result: Dict[str, Any],
    *,
    max_cloud_pct: int,
    ndwi_threshold: float,
    algorithm_version: str,
) -> Tuple[SatelliteObservation, bool]:
    """Insert or update one monthly record. Idempotent by identity tuple.

    The identity uses the **requested** threshold, not the value echoed back by the
    remote computation, so a threshold cannot silently change the record it updates.
    """
    existing = (
        db.query(SatelliteObservation)
        .filter(
            *identity_filter(
                row_aoi.id,
                collection=result["collection"],
                algorithm_version=algorithm_version,
                ndwi_threshold=ndwi_threshold,
                max_cloud_pct=max_cloud_pct,
            ),
            SatelliteObservation.month == result["month"],
        )
        .first()
    )

    fields = dict(
        period_start=result["period_start"],
        period_end=result["period_end"],
        sensor=result.get("sensor"),
        resolution_m=result.get("resolution_m"),
        ndwi_mean=result.get("ndwi_mean"),
        ndwi_median=result.get("ndwi_median"),
        water_area_km2=result.get("water_area_km2"),
        water_fraction=result.get("water_fraction"),
        scene_count=int(result.get("scene_count") or 0),
        valid_pixel_count=result.get("valid_pixel_count"),
        status=result["status"],
        mask_rule="SCL in (0,1,3,8,9,10,11) excluded",
        quality_json=json.dumps(
            {"cloud_filter_pct": int(max_cloud_pct), "cloud_mask": "SCL", "composite": "median"},
            sort_keys=True,
        ),
        computed_at=datetime.now(timezone.utc),
    )

    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing, False

    row = SatelliteObservation(
        aoi_id=row_aoi.id,
        month=result["month"],
        collection=result["collection"],
        ndwi_threshold=float(ndwi_threshold),
        max_cloud_pct=int(max_cloud_pct),
        algorithm=result.get("algorithm") or indices.ALGORITHM,
        algorithm_version=algorithm_version,
        **fields,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = (
            db.query(SatelliteObservation)
            .filter(
                *identity_filter(
                    row_aoi.id,
                    collection=result["collection"],
                    algorithm_version=algorithm_version,
                    ndwi_threshold=ndwi_threshold,
                    max_cloud_pct=max_cloud_pct,
                ),
                SatelliteObservation.month == result["month"],
            )
            .one()
        )
        return row, False
    db.refresh(row)
    return row, True


def fetch_month(
    db: Session,
    row_aoi: SatelliteAOI,
    month: str,
    *,
    ndwi_threshold: float,
    max_cloud_pct: int,
    algorithm_version: str = indices.ALGORITHM_VERSION,
) -> Tuple[SatelliteObservation, bool]:
    """Fetch one month from Earth Engine and persist it."""
    result = gee.monthly_ndwi(
        aoi_geometry(row_aoi),
        month,
        ndwi_threshold=ndwi_threshold,
        max_cloud_pct=max_cloud_pct,
    )
    return _upsert_observation(
        db,
        row_aoi,
        result,
        max_cloud_pct=max_cloud_pct,
        ndwi_threshold=ndwi_threshold,
        algorithm_version=algorithm_version,
    )


# ------------------------------------------------------------------------- jobs


def find_active_job(
    db: Session,
    *,
    aoi_id: int,
    ndwi_threshold: float,
    max_cloud_pct: int,
    start_month: str,
    end_month: str,
) -> Optional[SatelliteFetchJob]:
    """Return a queued/running job for the same AOI, request parameters and overlapping months.

    Used to avoid stacking duplicate workers on one AOI: the dashboard polls one job, and a
    second identical request would fetch the same months twice.
    """
    return (
        db.query(SatelliteFetchJob)
        .filter(
            SatelliteFetchJob.aoi_id == aoi_id,
            SatelliteFetchJob.status.in_(ACTIVE_STATUSES),
            SatelliteFetchJob.ndwi_threshold == float(ndwi_threshold),
            SatelliteFetchJob.max_cloud_pct == int(max_cloud_pct),
            SatelliteFetchJob.start_month <= end_month,
            SatelliteFetchJob.end_month >= start_month,
        )
        .order_by(SatelliteFetchJob.id.asc())
        .first()
    )


def recover_interrupted_jobs(session: Optional[Session] = None) -> List[int]:
    """Mark jobs abandoned by a previous backend process as interrupted.

    A job row with an active status is only trustworthy while a worker exists in this process,
    so anything active at startup belongs to a dead process. Progress counters, timings and
    detail are preserved; no job is deleted and no new job is started here.
    """
    owns_session = session is None
    session = session or SessionLocal()
    try:
        stale = [
            job
            for job in session.query(SatelliteFetchJob)
            .filter(SatelliteFetchJob.status.in_(ACTIVE_STATUSES))
            .all()
            if job.id not in _ACTIVE_JOB_IDS
        ]
        if not stale:
            return []

        now = datetime.now(timezone.utc)
        recovered: List[int] = []
        for job in stale:
            processed = int(job.months_completed or 0) + int(job.months_failed or 0)
            job.status = STATUS_INTERRUPTED
            job.finished_at = now
            job.error = (
                f"Retrieval was interrupted after {processed} of {int(job.months_total or 0)} "
                "month(s) because the backend restarted. Already stored months are kept; "
                "request the history again to fetch only the remaining months."
            )
            recovered.append(job.id)
        session.commit()
        return recovered
    finally:
        if owns_session:
            session.close()


def _job_payload(job: SatelliteFetchJob) -> Dict[str, Any]:
    return {
        "id": job.id,
        "aoi_id": job.aoi_id,
        "status": job.status,
        "start_month": job.start_month,
        "end_month": job.end_month,
        "ndwi_threshold": job.ndwi_threshold,
        "max_cloud_pct": job.max_cloud_pct,
        "months_total": job.months_total,
        "months_completed": job.months_completed,
        "months_skipped": job.months_skipped,
        "months_failed": job.months_failed,
        "error": job.error,
        "detail": json.loads(job.detail_json) if job.detail_json else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def job_status(db: Session, job_id: int) -> Dict[str, Any]:
    job = db.get(SatelliteFetchJob, job_id)
    if job is None:
        raise LookupError(f"Satellite fetch job {job_id} not found.")
    return _job_payload(job)


def start_fetch(
    db: Session,
    row_aoi: SatelliteAOI,
    *,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    months: Optional[int] = None,
    ndwi_threshold: Optional[float] = None,
    max_cloud_pct: Optional[int] = None,
    force: bool = False,
    run_async: bool = True,
) -> SatelliteFetchJob:
    """Create a fetch job for the months that are still missing.

    Historical computation never runs inline in a normal request; it is dispatched to a
    daemon thread and its progress is persisted on the job row.
    """
    collection = settings.SATELLITE_COLLECTION
    algorithm_version = indices.ALGORITHM_VERSION
    threshold = indices.NDWI_THRESHOLD_DEFAULT if ndwi_threshold is None else float(ndwi_threshold)
    cloud = indices.MAX_CLOUD_PCT_DEFAULT if max_cloud_pct is None else int(max_cloud_pct)

    if not -1.0 <= threshold <= 1.0:
        raise ValueError("NDWI threshold must be between -1 and 1.")
    if not 0 <= cloud <= 100:
        raise ValueError("Cloud filter must be between 0 and 100 percent.")

    if start_month is None or end_month is None:
        default_start, default_end = indices.default_window(
            months or settings.SATELLITE_DEFAULT_MONTHS
        )
        start_month = start_month or default_start
        end_month = end_month or default_end

    all_months = indices.month_sequence(start_month, end_month)

    # One worker per AOI/parameter/window: return the in-flight job instead of starting a
    # second one that would fetch the same months concurrently.
    if run_async:
        running = find_active_job(
            db,
            aoi_id=row_aoi.id,
            ndwi_threshold=threshold,
            max_cloud_pct=cloud,
            start_month=start_month,
            end_month=end_month,
        )
        if running is not None:
            setattr(running, "reused_active_job", True)
            return running

    if force:
        missing = list(all_months)
    else:
        present = stored_months(
            db,
            row_aoi.id,
            collection=collection,
            algorithm_version=algorithm_version,
            ndwi_threshold=threshold,
            max_cloud_pct=cloud,
        )
        missing = [month for month in all_months if month not in present]

    job = SatelliteFetchJob(
        aoi_id=row_aoi.id,
        status=STATUS_QUEUED,
        start_month=start_month,
        end_month=end_month,
        ndwi_threshold=threshold,
        max_cloud_pct=cloud,
        months_total=len(missing),
        months_skipped=len(all_months) - len(missing),
    )

    if not missing:
        job.status = STATUS_COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        job.detail_json = json.dumps(
            {"message": "All requested months were already stored; nothing to fetch."}
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    db.add(job)
    db.commit()
    db.refresh(job)

    if run_async:
        _register_active(job.id)
        thread = threading.Thread(
            target=_run_job_safely, args=(job.id, missing, threshold, cloud, algorithm_version), daemon=True
        )
        thread.start()
    else:
        # Inline execution (tests, CLI backfills) reuses the caller's session so an
        # isolated test database is never bypassed in favour of the global engine.
        _execute_job(job.id, missing, threshold, cloud, algorithm_version, session=db)

    db.refresh(job)
    return job


def _run_job_safely(
    job_id: int,
    months: Sequence[str],
    threshold: float,
    cloud: int,
    algorithm_version: str,
) -> None:
    session = SessionLocal()
    try:
        _execute_job(job_id, months, threshold, cloud, algorithm_version, session=session)
    except Exception:  # noqa: BLE001 - the job row already records the failure
        pass
    finally:
        _unregister_active(job_id)
        session.close()


def _execute_job(
    job_id: int,
    months: Sequence[str],
    threshold: float,
    cloud: int,
    algorithm_version: str,
    session: Optional[Session] = None,
) -> None:
    """Run a job. Background threads pass their own session; inline runs reuse the caller's."""
    owns_session = session is None
    session = session or SessionLocal()
    _register_active(job_id)
    try:
        job = session.get(SatelliteFetchJob, job_id)
        if job is None:
            return
        row_aoi = session.get(SatelliteAOI, job.aoi_id)
        if row_aoi is None:
            job.status = STATUS_FAILED
            job.error = "Area of interest no longer exists."
            job.finished_at = datetime.now(timezone.utc)
            session.commit()
            return

        job.status = STATUS_RUNNING
        job.started_at = datetime.now(timezone.utc)
        session.commit()

        completed = failed = 0
        failures: List[Dict[str, str]] = []

        for month in months:
            try:
                fetch_month(
                    session,
                    row_aoi,
                    month,
                    ndwi_threshold=threshold,
                    max_cloud_pct=cloud,
                    algorithm_version=algorithm_version,
                )
                completed += 1
            except gee.GeeUnavailable as error:
                session.rollback()
                job.status = STATUS_FAILED
                job.error = str(error)
                job.months_completed = completed
                job.months_failed = failed
                job.finished_at = datetime.now(timezone.utc)
                session.commit()
                return
            except (gee.GeeQueryError, ValueError) as error:
                session.rollback()
                failed += 1
                failures.append({"month": month, "error": str(error)})
            except Exception as error:  # noqa: BLE001
                session.rollback()
                failed += 1
                failures.append({"month": month, "error": f"{type(error).__name__}: {error}"})

            job.months_completed = completed
            job.months_failed = failed
            session.commit()

        job.status = STATUS_COMPLETED
        job.months_completed = completed
        job.months_failed = failed
        job.detail_json = (
            json.dumps({"failures": failures, "months_requested": len(months)}) if failures else None
        )
        if failed and not completed:
            job.status = STATUS_FAILED
            job.error = (
                "Earth Engine returned no usable results for any requested month. "
                "See detail for per-month errors."
            )
        job.finished_at = datetime.now(timezone.utc)
        session.commit()
    finally:
        _unregister_active(job_id)
        if owns_session:
            session.close()
