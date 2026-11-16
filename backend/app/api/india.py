"""Authenticated India-only monitoring workflows; no seeded monitoring locations."""
import hashlib
import json
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session
from ..core.config import settings
from ..db.session import get_db
from ..india_models import IndiaStation, IndiaObservation, IndiaRecord
from ..india_analysis import build_reference, compare, LIMITATIONS, MIN_REFERENCE
from ..ml.feature_extractor import reconstruct_20_features
from ..ml.inference import get_inference_engine
from .deps import get_current_user


def india_user(user=Depends(get_current_user)):
    if user.workspace != 'india':
        raise HTTPException(403, 'This resource belongs to the Indian workspace.')
    return user


router = APIRouter(prefix='/india', tags=['Indian workspace'], dependencies=[Depends(india_user)])


@lru_cache(maxsize=1)
def _ganga_snapshot():
    return json.loads(Path(__file__).resolve().parents[1].joinpath('ganga_2012.json').read_text(encoding='utf-8-sig'))


@router.get('/historical/ganga')
def ganga_historical(offset: int = Query(0, ge=0, le=10000)):
    snapshot = _ganga_snapshot()
    records = snapshot['records']
    return {
        'records': records[offset:offset + 10],
        'labels': snapshot['labels'],
        'has_more': offset + 10 < len(records),
        'available_total': len(records),
        'source_total': snapshot['source_total'],
    }


FILES = settings.UPLOAD_DIR.parent / 'india_samples'
Season = Literal['Pre-monsoon', 'Monsoon', 'Post-monsoon', 'Winter', 'Unspecified']


class StrictInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True)


class StationInput(StrictInput):
    name: str = Field(min_length=2, max_length=160)
    river: Literal['', 'Ganga', 'Mahanadi', 'Godavari', 'Narmada'] = ''
    state: str = Field(min_length=2, max_length=80)
    latitude: float = Field(ge=6, le=38)
    longitude: float = Field(ge=68, le=98)
    coordinate_source: str = Field(min_length=4, max_length=500)


GROUND_CAPTURE_VALIDATION = {'capture_clock_skew': timedelta(minutes=5)}


class SampleMetadata(StrictInput):
    timestamp: datetime
    season: Season
    camera: str = Field(min_length=2, max_length=160)
    illumination: str = Field(min_length=2, max_length=300)
    preparation: str = Field(min_length=2, max_length=500)
    capture_protocol: str = Field(min_length=2, max_length=300)
    camera_settings: str = Field(min_length=2, max_length=500)
    eligible: bool = False
    notes: str = Field(default='', max_length=2000)

    @field_validator('timestamp')
    @classmethod
    def timezone_required(cls, value, info):
        if value.tzinfo is None:
            raise ValueError('Sampling timestamp must include a timezone.')
        clock_skew = (info.context or {}).get('capture_clock_skew', timedelta())
        if value > datetime.now(timezone.utc) + clock_skew:
            if clock_skew:
                raise ValueError('Capture time is ahead of the server. Enable automatic date and time on the phone and PC, then retry once the server clock has caught up.')
            raise ValueError('Sampling timestamp cannot be in the future.')
        return value


class ReferenceInput(StrictInput):
    observation_ids: list[int] = Field(min_length=5, max_length=500)
    season: Season
    capture_protocol: str = Field(min_length=2, max_length=300)
    notes: str = Field(min_length=4, max_length=2000)


class EvidenceInput(StrictInput):
    observation_id: Optional[int] = None
    parameter: str = Field(min_length=2, max_length=100)
    value: float
    unit: str = Field(min_length=1, max_length=50)
    timestamp: datetime
    provenance: str = Field(min_length=4, max_length=500)
    notes: str = Field(default='', max_length=2000)

    @field_validator('timestamp')
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError('Measurement timestamp must include a timezone.')
        return value


class ActionInput(StrictInput):
    observation_id: Optional[int] = None
    concern: str = Field(min_length=4, max_length=300)
    evidence: str = Field(min_length=4, max_length=2000)
    suggested_action: str = Field(min_length=4, max_length=2000)
    priority: Literal['Routine', 'Review', 'High'] = 'Review'


class ActionUpdate(StrictInput):
    status: Literal['Open', 'Reviewed', 'In progress', 'Completed']
    remarks: str = Field(default='', max_length=2000)


def unpack(record):
    return {**json.loads(record.payload), 'id': record.id}


def require_station(db, station_id):
    station = db.get(IndiaStation, station_id)
    if not station:
        raise HTTPException(404, 'Indian monitoring station not found.')
    return station


def observations(db, station_id):
    rows = db.query(IndiaObservation).filter_by(station_id=station_id).all()
    return sorted([unpack(row) for row in rows], key=lambda o: o['timestamp'], reverse=True)


def records(db, station_id, kind):
    return [unpack(row) for row in db.query(IndiaRecord).filter_by(station_id=station_id, kind=kind).order_by(IndiaRecord.id.desc()).all()]


def save_record(db, station_id, kind, payload):
    row = IndiaRecord(station_id=station_id, kind=kind, payload=json.dumps(payload, allow_nan=False))
    db.add(row)
    db.commit()
    db.refresh(row)
    return unpack(row)


@router.get('/stations')
def list_stations(db: Session = Depends(get_db)):
    return [unpack(row) for row in db.query(IndiaStation).order_by(IndiaStation.id).all()]


@router.post('/stations', status_code=201)
def register_station(body: StationInput, db: Session = Depends(get_db)):
    row = IndiaStation(payload=json.dumps({**body.model_dump(), 'coordinate_status': 'Operator-registered; source recorded', 'country': 'India'}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return unpack(row)


@router.post('/stations/{station_id}/observations', status_code=201)
async def upload_observation(station_id: int, metadata: str = Form(...), image: UploadFile = File(...), db: Session = Depends(get_db)):
    return await store_observation(station_id, metadata, image, db)


async def store_observation(station_id, metadata, image, db, ground=None):
    require_station(db, station_id)
    try:
        meta = SampleMetadata.model_validate_json(
            metadata, context=GROUND_CAPTURE_VALIDATION if ground is not None else None,
        )
    except ValueError as error:
        raise HTTPException(422, f'Invalid sample metadata: {error}')
    contents = await image.read(12 * 1024 * 1024 + 1)
    if not contents or len(contents) > 12 * 1024 * 1024:
        raise HTTPException(413, 'Choose an image between 1 byte and 12 MB.')
    checksum = hashlib.sha256(contents).hexdigest()
    if db.query(IndiaObservation).filter_by(station_id=station_id, checksum=checksum).first():
        raise HTTPException(409, 'This image is already recorded at this station. Duplicate images cannot strengthen a baseline.')
    decoded = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise HTTPException(422, 'The uploaded file is not a decodable water sample image.')
    mime = ('image/png' if contents.startswith(b'\x89PNG\r\n\x1a\n') else
            'image/jpeg' if contents.startswith(b'\xff\xd8\xff') else
            'image/webp' if contents.startswith(b'RIFF') and contents[8:12] == b'WEBP' else None)
    if mime is None:
        raise HTTPException(422, 'Use a PNG, JPEG or WebP image.')
    features = reconstruct_20_features(decoded)
    if not all(math.isfinite(float(v)) for v in features.values()):
        raise HTTPException(422, 'Extracted features contain invalid numeric values.')
    classification, processing_error = None, None
    try:
        classification = get_inference_engine().classify_dict(features)
    except Exception:
        processing_error = 'RF classification unavailable. The original image and extracted features are retained.'
    filename = uuid.uuid4().hex + '.image'
    FILES.mkdir(parents=True, exist_ok=True)
    path = FILES / filename
    path.write_bytes(contents)
    payload = {**meta.model_dump(mode='json'), 'timestamp': meta.timestamp.astimezone(timezone.utc).isoformat(),
               'features': features, 'classification': classification, 'processing_error': processing_error,
               'processing_status': 'features_extracted' if processing_error else 'completed', 'checksum': checksum,
               'feature_extractor_version': 'opencv-20feat-v1.0.0', 'media_type': mime}
    if ground is not None:
        payload['ground'] = ground
    row = IndiaObservation(station_id=station_id, checksum=checksum, filename=filename, payload=json.dumps(payload, allow_nan=False))
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return unpack(row)


@router.get('/observations/{observation_id}/image')
def sample_image(observation_id: int, db: Session = Depends(get_db)):
    row = db.get(IndiaObservation, observation_id)
    if not row or not (FILES / row.filename).is_file():
        raise HTTPException(404, 'Original sample image unavailable.')
    return FileResponse(FILES / row.filename, media_type=json.loads(row.payload).get('media_type', 'image/jpeg'), headers={'Cache-Control': 'private, no-store'})


@router.post('/stations/{station_id}/fingerprint', status_code=201)
def create_reference(station_id: int, body: ReferenceInput, db: Session = Depends(get_db)):
    require_station(db, station_id)
    available = {o['id']: o for o in observations(db, station_id)}
    ids = set(body.observation_ids)
    if len(ids) < MIN_REFERENCE or any(i not in available for i in ids):
        raise HTTPException(422, 'Select at least five distinct observations belonging to this station.')
    selected = [available[i] for i in sorted(ids)]
    if any(not o['eligible'] or o['season'] != body.season or o['capture_protocol'] != body.capture_protocol for o in selected):
        raise HTTPException(422, 'References must be explicitly eligible and share the selected season and capture protocol.')
    capture_settings = {key: selected[0][key] for key in ('camera', 'camera_settings', 'illumination', 'preparation')}
    if any(any(o[key] != value for key, value in capture_settings.items()) for o in selected):
        raise HTTPException(422, 'Reference camera, settings, illumination and preparation must match exactly. Use separate capture protocols for different acquisition settings.')
    try:
        stats = build_reference(selected)
    except ValueError as error:
        raise HTTPException(422, str(error))
    return save_record(db, station_id, 'baseline', {**body.model_dump(), 'observation_ids': sorted(ids), 'stats': stats,
                        'sample_count': len(selected), 'capture_settings': capture_settings, 'status': 'provisional', 'method': 'station-median-iqr-v1',
                        'start': min(o['timestamp'] for o in selected), 'end': max(o['timestamp'] for o in selected),
                        'created_at': datetime.now(timezone.utc).isoformat(), 'limitations': LIMITATIONS})


@router.post('/stations/{station_id}/evidence/{kind}', status_code=201)
def add_evidence(station_id: int, kind: Literal['laboratory', 'context'], body: EvidenceInput, db: Session = Depends(get_db)):
    require_station(db, station_id)
    if body.observation_id is not None:
        obs = db.get(IndiaObservation, body.observation_id)
        if not obs or obs.station_id != station_id:
            raise HTTPException(422, 'The paired observation must belong to this station.')
    payload = body.model_dump(mode='json')
    payload['timestamp'] = body.timestamp.astimezone(timezone.utc).isoformat()
    payload['measurement_type'] = 'Measured laboratory result' if kind == 'laboratory' else 'Operator-entered contextual measurement'
    return save_record(db, station_id, kind, payload)


@router.post('/stations/{station_id}/actions', status_code=201)
def add_action(station_id: int, body: ActionInput, db: Session = Depends(get_db)):
    require_station(db, station_id)
    if body.observation_id is not None:
        observation = db.get(IndiaObservation, body.observation_id)
        if not observation or observation.station_id != station_id:
            raise HTTPException(422, 'Action evidence must belong to this station.')
    return save_record(db, station_id, 'action', {**body.model_dump(), 'status': 'Open', 'remarks': '', 'history': [],
                       'created_at': datetime.now(timezone.utc).isoformat(), 'priority_basis': 'Operator-assigned monitoring priority'})


@router.patch('/actions/{action_id}')
def update_action(action_id: int, body: ActionUpdate, db: Session = Depends(get_db)):
    row = db.get(IndiaRecord, action_id)
    if not row or row.kind != 'action':
        raise HTTPException(404, 'Indian monitoring action not found.')
    payload = unpack(row)
    payload['history'].append({**body.model_dump(), 'timestamp': datetime.now(timezone.utc).isoformat()})
    row.payload = json.dumps({**payload, **body.model_dump()})
    db.commit()
    return unpack(row)


@router.get('/stations/{station_id}/analysis')
def station_analysis(station_id: int, observation_id: Optional[int] = None,
                     start: Optional[datetime] = None, end: Optional[datetime] = None, db: Session = Depends(get_db)):
    station = unpack(require_station(db, station_id))
    all_samples = observations(db, station_id)
    if any(value and value.tzinfo is None for value in (start, end)):
        raise HTTPException(422, 'Date filters must include a timezone.')
    if start and end and start > end:
        raise HTTPException(422, 'Start date must precede the end date.')
    samples = [o for o in all_samples if (not start or datetime.fromisoformat(o['timestamp']) >= start)
               and (not end or datetime.fromisoformat(o['timestamp']) <= end)]
    current = next((o for o in samples if o['id'] == observation_id), None) if observation_id else (samples[0] if samples else None)
    if observation_id and current is None:
        raise HTTPException(404, 'Selected observation is not available in this station and period.')
    baselines = records(db, station_id, 'baseline')
    reference = next((b for b in baselines if current and b['season'] == current['season'] and b['capture_protocol'] == current['capture_protocol']), None)
    previous = samples[samples.index(current) + 1] if current and samples.index(current) + 1 < len(samples) else None
    comparison = compare(current, reference, previous) if current else None
    timeline = []
    for sample in reversed(samples):
        result = compare(sample, reference) if reference else None
        timeline.append({'id': sample['id'], 'timestamp': sample['timestamp'], 'anomaly_score': result['anomaly_score'] if result and not result['is_reference_sample'] else None,
                         'visual_stability_score': result['visual_stability_score'] if result else None, 'status': result['status'] if result else 'insufficient_baseline',
                         'feature_deviations': {
                             f['name']: f['normalized_deviation'] for f in result['features']
                         } if result and not result['is_reference_sample'] else {}})
    # Persistence refers only to consecutive, independent observations in this reference context.
    recent = [compare(o, reference) for o in samples[samples.index(current):samples.index(current)+3]] if current and reference else []
    persistent = len(recent) == 3 and all(r['status'] == 'potential_anomaly' for r in recent)
    if comparison:
        comparison['persistent_screening_flag'] = persistent
    return {'station': station, 'observations': samples, 'current': current, 'previous': previous,
            'reference': reference, 'reference_observation': next((o for o in all_samples if reference and o['id'] in reference['observation_ids']), None),
            'baselines': baselines, 'comparison': comparison, 'timeline': timeline,
            'laboratory': records(db, station_id, 'laboratory'), 'context': records(db, station_id, 'context'),
            'actions': records(db, station_id, 'action'), 'limitations': LIMITATIONS}


@router.get('/stations/{station_id}/report')
def export_report(station_id: int, observation_id: Optional[int] = None,
                  start: Optional[datetime] = None, end: Optional[datetime] = None, db: Session = Depends(get_db)):
    evidence = station_analysis(station_id, observation_id, start, end, db)
    text = ('AQUALENS AI — INDIAN STATION RESEARCH REPORT\n'
            f'Exported: {datetime.now(timezone.utc).isoformat()}\n'
            'All timestamps below are ISO 8601. Original images are retained in the authenticated sample archive.\n\n'
            + json.dumps(evidence, indent=2, ensure_ascii=False, allow_nan=False))
    return Response(text, media_type='text/plain', headers={'Content-Disposition': f'attachment; filename="aqualens-india-station-{station_id}.txt"', 'Cache-Control': 'no-store'})

from .. import india_datasets as datasets


@router.get('/datasets/measurements/{river}')
def dataset_measurements(river: Literal['ganga', 'mahanadi']):
    filename = {'ganga': 'RS_Session_269_AU_1674_B_i.csv',
                'mahanadi': 'water_quality_of_river_mahanadi-2014.csv'}[river]
    try:
        return datasets.measurements(filename)
    except FileNotFoundError:
        raise HTTPException(404, 'The measurement CSV is not installed.')


@router.get('/datasets/census')
def dataset_census(file: str = '', offset: int = Query(0, ge=0, le=1000000)):
    if not file:
        return {'files': [path.name for path in datasets.census_files()]}
    page = datasets.census_page(file, offset)
    if page is None:
        raise HTTPException(404, 'Census file not found.')
    return page


@router.get('/datasets/satellite')
def dataset_satellite(offset: int = Query(0, ge=0, le=10000)):
    names = list(datasets.satellite_images())
    return {'items': names[offset:offset + 20], 'total': len(names)}


@router.get('/datasets/satellite/{name}/image')
def dataset_satellite_image(name: str):
    path = datasets.satellite_images().get(name)
    if path is None:
        raise HTTPException(404, 'Satellite image not found.')
    return FileResponse(path, media_type='image/jpeg')


@router.get('/datasets/satellite/{name}/features')
def dataset_satellite_features(name: str):
    if name not in datasets.satellite_images():
        raise HTTPException(404, 'Satellite image not found.')
    features = datasets.satellite_features(name)
    if features is None:
        raise HTTPException(422, 'Satellite JPEG could not be decoded.')
    return {**features, 'location': datasets.satellite_location(name)}

@router.get('/earthdata/scenes')
def earthdata_scenes(latitude: float = Query(ge=7, le=38), longitude: float = Query(ge=67, le=98)):
    from ..earthdata import scenes
    try:
        return scenes(latitude, longitude)
    except (OSError, ValueError, KeyError):
        raise HTTPException(502, 'NASA Earthdata catalog could not be reached. Try again.')

@router.get('/earthdata/profile')
def earthdata_profile(latitude: float = Query(ge=7, le=38), longitude: float = Query(ge=67, le=98)):
    from ..earthdata import water_profile
    try:
        return water_profile(latitude, longitude)
    except ImportError:
        raise HTTPException(503, 'Install rasterio on the backend to analyze OPERA GeoTIFFs.')

@router.post('/earthdata/profile')
def build_earthdata_profile(latitude: float = Query(ge=7, le=38), longitude: float = Query(ge=67, le=98)):
    from ..earthdata import build_profile
    try:
        return build_profile(latitude, longitude)
    except ImportError:
        raise HTTPException(503, 'Install rasterio on the backend to analyze OPERA GeoTIFFs.')
    except PermissionError:
        raise HTTPException(503, 'Set a fresh NASA_EARTHDATA token in backend/.env.')
    except (OSError, ValueError, KeyError):
        raise HTTPException(502, 'Unable to retrieve NASA Earthdata scenes.')

@router.get('/laboratory/water-health')
def laboratory_water_health(river: str = '', station: str = '', state: str = '',
                            start: date | None = None, end: date | None = None,
                            db: Session = Depends(get_db)):
    from ..laboratory_wqi import assessment, persist_assessment

    if start and end and start > end:
        raise HTTPException(422, 'Start date must precede the end date.')
    result = assessment(river, station, start, end, state, db=db)
    if (river or station) and (result['scored_stations'] or result['partial_scored_stations']):
        persist_assessment(db, result, river=river, station=station, start=start, end=end, state=state)
    return result


class LaboratoryApproval(StrictInput):
    report_reference: str = Field(min_length=4, max_length=500)
    sample_id: str = Field(min_length=1, max_length=160)


@router.post('/stations/{station_id}/evidence/laboratory/{record_id}/approval')
def approve_laboratory_result(station_id: int, record_id: int, approval: LaboratoryApproval,
                              reviewer=Depends(india_user), db: Session = Depends(get_db)):
    from ..laboratory_wqi import approved_reading

    row = db.get(IndiaRecord, record_id)
    if not row or row.station_id != station_id or row.kind != 'laboratory':
        raise HTTPException(404, 'Laboratory result not found at this station.')
    payload = json.loads(row.payload)
    if not approved_reading(payload):
        raise HTTPException(422, 'Check the parameter name, measurement and unit against CPCB Class B objectives.')
    if payload.get('wqi_approval'):
        raise HTTPException(409, 'This result has already been reviewed.')
    payload['wqi_approval'] = {
        **approval.model_dump(),
        'reviewed_by': reviewer.username,
        'reviewed_at': datetime.now(timezone.utc).isoformat(),
    }
    row.payload = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    db.commit()
    return unpack(row)
