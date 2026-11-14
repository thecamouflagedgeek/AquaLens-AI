"""Authenticated smartphone ingestion and India admin review."""
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import Field, ValidationError
from sqlalchemy.orm import Session

from .deps import get_current_user
from .india import GROUND_CAPTURE_VALIDATION
from .india import SampleMetadata, IndiaObservation, get_db, require_station, unpack, store_observation, station_analysis, list_stations, sample_image

router = APIRouter(prefix='/india/ground', tags=['Ground monitoring'])


def officer(user=Depends(get_current_user)):
    if user.role != 'officer' and not (user.workspace == 'india'):
        raise HTTPException(403, 'Field officer access required.')
    return user


def admin(user=Depends(get_current_user)):
    if user.workspace != 'india':
        raise HTTPException(403, 'India admin access required.')


class GroundMetadata(SampleMetadata):
    latitude: float = Field(ge=6, le=38)
    longitude: float = Field(ge=68, le=98)
    accuracy_m: float = Field(gt=0, le=1000)
    capture_id: str | None = Field(default=None, pattern=r'^[a-f0-9-]{36}$')
    sample_type: str | None = Field(default=None, max_length=100)


@router.get('/stations', dependencies=[Depends(officer)])
def upload_stations(db: Session = Depends(get_db)):
    return list_stations(db)


def distance_m(lat, lon, station):
    dlat, dlon = radians(station['latitude']-lat), radians(station['longitude']-lon)
    h = sin(dlat/2)**2 + cos(radians(lat))*cos(radians(station['latitude']))*sin(dlon/2)**2
    return 12742000 * asin(sqrt(min(1, h)))


@router.post('/stations/{station_id}/observations', status_code=201)
async def upload(station_id: int, metadata: str = Form(...), image: UploadFile = File(...),
                 db: Session = Depends(get_db), user=Depends(officer)):
    station = unpack(require_station(db, station_id))
    try:
        meta = GroundMetadata.model_validate_json(metadata, context=GROUND_CAPTURE_VALIDATION)
    except ValidationError as error:
        problems = [
            f"{'.'.join(map(str, issue['loc'])) or 'metadata'}: {issue['msg']}"
            for issue in error.errors(include_input=False, include_context=False)
        ]
        raise HTTPException(422, 'Invalid capture metadata. ' + '; '.join(problems)) from error
    distance = distance_m(meta.latitude, meta.longitude, station)
    if meta.capture_id:
        for row in db.query(IndiaObservation).filter_by(station_id=station_id):
            existing = unpack(row)
            provenance = existing.get('ground') or {}
            if provenance.get('officer_id') == user.id and provenance.get('capture_id') == meta.capture_id:
                return dict(existing, station_id=row.station_id)
    ground = dict(latitude=meta.latitude, longitude=meta.longitude, accuracy_m=meta.accuracy_m,
                  distance_m=round(distance, 1), officer_id=user.id, officer=user.username,
                  uploaded_at=datetime.now(timezone.utc).isoformat(), location_status='review_required',
                  capture_id=meta.capture_id, sample_type=meta.sample_type)
    capture = meta.model_dump(mode='json', exclude={'latitude','longitude','accuracy_m'})
    capture['eligible'] = False
    result = await store_observation(station_id, json.dumps(capture), image, db, ground=ground)
    return dict(result, station_id=station_id)


@router.get('/mine')
def my_observations(db: Session = Depends(get_db), user=Depends(officer)):
    return [item for item in list_ground(db) if item['ground'].get('officer_id') == user.id]


def own_observation(db, observation_id, user):
    row = db.get(IndiaObservation, observation_id)
    if not row or (unpack(row).get('ground') or {}).get('officer_id') != user.id:
        raise HTTPException(404, 'Observation not found.')
    return row


@router.get('/mine/{observation_id}/image')
def my_image(observation_id: int, db: Session = Depends(get_db), user=Depends(officer)):
    own_observation(db, observation_id, user)
    return sample_image(observation_id, db)


@router.get('/mine/{observation_id}/analysis')
def my_analysis(observation_id: int, db: Session = Depends(get_db), user=Depends(officer)):
    own_observation(db, observation_id, user)
    result = analysis(observation_id, db)
    return {key: result[key] for key in ('comparison', 'reference')}


@router.get('/observations', dependencies=[Depends(admin)])
def list_ground(db: Session = Depends(get_db)):
    # Restrict to explicitly geotagged field uploads; legacy images have no officer GPS provenance.
    return [item for row in db.query(IndiaObservation).order_by(IndiaObservation.id.desc())
            if (item := dict(unpack(row), station_id=row.station_id)).get('ground')]


@router.post('/observations/{observation_id}/verify-location', dependencies=[Depends(admin)])
def verify_location(observation_id: int, db: Session = Depends(get_db)):
    row = db.get(IndiaObservation, observation_id)
    payload = json.loads(row.payload) if row else None
    if not payload or not payload.get('ground'):
        raise HTTPException(404, 'Ground observation not found.')
    payload['ground']['location_status'] = 'admin_verified'
    row.payload = json.dumps(payload, allow_nan=False)
    db.commit()
    return unpack(row)


@router.get('/observations/{observation_id}/analysis', dependencies=[Depends(admin)])
def analysis(observation_id: int, db: Session = Depends(get_db)):
    row = db.get(IndiaObservation, observation_id)
    if not row or not unpack(row).get('ground'):
        raise HTTPException(404, 'Ground observation not found.')
    verified = unpack(row)['ground']['location_status'] == 'admin_verified'
    result = station_analysis(row.station_id, observation_id=observation_id, db=db)
    return {
        'comparison': result['comparison'] if verified else None,
        'reference': result['reference'] if verified else None,
        'laboratory': result['laboratory'],
        'context': result['context'],
    }

