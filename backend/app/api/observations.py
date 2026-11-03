"""
AquaLens AI - Observations & Model Inference API Endpoints
Handles image ingestion, feature extraction, classification, and observation history.
"""

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import cv2
import numpy as np
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.session import get_db
from ..db.models import (
    MonitoringStation,
    Observation,
    FeatureVector,
    Classification,
    AnomalyResult,
    WaterHealthScore,
    User,
    AuditLog,
)
from ..schemas.schemas import (
    ObservationOut,
    ClassificationOut,
    FeatureVectorOut,
)
from ..ml.feature_extractor import reconstruct_20_features, feature_dict_to_vector
from ..ml.inference import get_inference_engine
from ..services.anomaly_service import AnomalyService
from ..services.health_score_service import HealthScoreService
from ..services.recommendation_service import RecommendationService
from .deps import get_current_user_optional, require_role

router = APIRouter(tags=["Observations & Inference"])


@router.post("/observations", response_model=ObservationOut, status_code=status.HTTP_201_CREATED)
async def create_observation(
    station_id: int = Form(...),
    sampling_timestamp: Optional[str] = Form(None),
    camera_model: Optional[str] = Form(None),
    illumination_condition: Optional[str] = Form(None),
    is_eligible_for_baseline: bool = Form(True),
    notes: Optional[str] = Form(None),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Ingests a new water image observation:
    1. Validates and saves the image file.
    2. Computes image SHA256 checksum.
    3. Extracts the exact 20 visual features.
    4. Evaluates the Objective 2 Random Forest classifier.
    5. Runs source-specific anomaly detection against station baseline.
    6. Updates Water Health Score & generated recommendations.
    """
    station = db.query(MonitoringStation).filter(MonitoringStation.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Monitoring station {station_id} not found.")

    # Read image contents
    contents = await image.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    # Compute checksum
    checksum = hashlib.sha256(contents).hexdigest()

    # Decode image with OpenCV
    nparr = np.frombuffer(contents, np.uint8)
    image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid or decodable image.")

    # Save to disk
    ext = Path(image.filename).suffix or ".jpg"
    filename = f"station_{station_id}_{checksum[:12]}_{int(datetime.now().timestamp())}{ext}"
    dest_path = settings.UPLOAD_DIR / filename
    with open(dest_path, "wb") as f:
        f.write(contents)

    # Parse sampling timestamp
    ts = datetime.now(timezone.utc)
    if sampling_timestamp:
        try:
            ts = datetime.fromisoformat(sampling_timestamp)
        except Exception:
            pass

    # Extract 20 features
    try:
        features_dict = reconstruct_20_features(image_bgr)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Feature extraction failed: {str(e)}")

    # Objective 2 Model Inference
    engine = get_inference_engine()
    inference_res = engine.classify_dict(features_dict)

    # Persist Observation
    obs = Observation(
        station_id=station_id,
        sampling_timestamp=ts,
        image_path=f"/uploads/{filename}",
        image_checksum=checksum,
        camera_model=camera_model,
        illumination_condition=illumination_condition,
        is_eligible_for_baseline=is_eligible_for_baseline,
        notes=notes,
    )
    db.add(obs)
    db.flush()

    # Persist Feature Vector
    feat_vec = FeatureVector(
        observation_id=obs.id,
        schema_version="20-features-v1.0",
        features_json=json.dumps(features_dict),
    )
    db.add(feat_vec)

    # Persist Classification
    clf = Classification(
        observation_id=obs.id,
        model_version=inference_res["model_version"],
        predicted_condition=inference_res["predicted_condition"],
        probabilities_json=json.dumps(inference_res["raw_probabilities"]),
    )
    db.add(clf)
    db.flush()

    # Trigger source-specific anomaly detection & Water Health Score
    anomaly_record = AnomalyService.save_or_update_anomaly(db, obs)
    health_record = HealthScoreService.save_or_update_score(db, obs, anomaly_record)
    RecommendationService.sync_recommendations(db, obs)

    db.commit()
    db.refresh(obs)

    return ObservationOut(
        id=obs.id,
        station_id=obs.station_id,
        sampling_timestamp=obs.sampling_timestamp,
        image_url=obs.image_path,
        camera_model=obs.camera_model,
        illumination_condition=obs.illumination_condition,
        is_eligible_for_baseline=obs.is_eligible_for_baseline,
        features=features_dict,
        classification=ClassificationOut(
            predicted_condition=clf.predicted_condition,
            probabilities=clf.get_probabilities(),
            model_version=clf.model_version,
            probability_note="Raw tree-vote probabilities; not calibrated confidence.",
            disclaimer="Visual condition classification only; does not evaluate potability.",
        ),
        created_at=obs.created_at,
    )


@router.get("/stations/{id}/observations", response_model=List[ObservationOut])
def list_station_observations(
    id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    st = db.query(MonitoringStation).filter(MonitoringStation.id == id).first()
    if not st:
        raise HTTPException(status_code=404, detail=f"Monitoring station {id} not found.")

    observations = (
        db.query(Observation)
        .filter(Observation.station_id == id)
        .order_by(Observation.sampling_timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for obs in observations:
        feats = obs.feature_vector.get_features() if obs.feature_vector else None
        clf_out = None
        if obs.classification:
            clf_out = ClassificationOut(
                predicted_condition=obs.classification.predicted_condition,
                probabilities=obs.classification.get_probabilities(),
                model_version=obs.classification.model_version,
                probability_note="Raw tree-vote probabilities; not calibrated confidence.",
                disclaimer="Visual condition classification only; does not evaluate potability.",
            )
        results.append(
            ObservationOut(
                id=obs.id,
                station_id=obs.station_id,
                sampling_timestamp=obs.sampling_timestamp,
                image_url=obs.image_path,
                camera_model=obs.camera_model,
                illumination_condition=obs.illumination_condition,
                is_eligible_for_baseline=obs.is_eligible_for_baseline,
                features=feats,
                classification=clf_out,
                created_at=obs.created_at,
            )
        )
    return results


@router.get("/observations/{id}", response_model=ObservationOut)
def get_observation(id: int, db: Session = Depends(get_db)):
    obs = db.query(Observation).filter(Observation.id == id).first()
    if not obs:
        raise HTTPException(status_code=404, detail=f"Observation {id} not found.")

    feats = obs.feature_vector.get_features() if obs.feature_vector else None
    clf_out = None
    if obs.classification:
        clf_out = ClassificationOut(
            predicted_condition=obs.classification.predicted_condition,
            probabilities=obs.classification.get_probabilities(),
            model_version=obs.classification.model_version,
            probability_note="Raw tree-vote probabilities; not calibrated confidence.",
            disclaimer="Visual condition classification only; does not evaluate potability.",
        )

    return ObservationOut(
        id=obs.id,
        station_id=obs.station_id,
        sampling_timestamp=obs.sampling_timestamp,
        image_url=obs.image_path,
        camera_model=obs.camera_model,
        illumination_condition=obs.illumination_condition,
        is_eligible_for_baseline=obs.is_eligible_for_baseline,
        features=feats,
        classification=clf_out,
        created_at=obs.created_at,
    )


@router.get("/observations/{id}/features", response_model=FeatureVectorOut)
def get_observation_features(id: int, db: Session = Depends(get_db)):
    obs = db.query(Observation).filter(Observation.id == id).first()
    if not obs:
        raise HTTPException(status_code=404, detail=f"Observation {id} not found.")
    if not obs.feature_vector:
        raise HTTPException(status_code=404, detail=f"Feature vector for observation {id} not found.")

    return FeatureVectorOut(
        schema_version=obs.feature_vector.schema_version,
        features=obs.feature_vector.get_features(),
    )


@router.post("/inference/classify")
async def adhoc_classify(
    image: UploadFile = File(...),
):
    """Ad-hoc direct inference on uploaded image without creating database record."""
    contents = await image.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Empty image provided.")
    nparr = np.frombuffer(contents, np.uint8)
    image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise HTTPException(status_code=400, detail="Invalid image encoding.")

    features = reconstruct_20_features(image_bgr)
    engine = get_inference_engine()
    result = engine.classify_dict(features)
    return result
