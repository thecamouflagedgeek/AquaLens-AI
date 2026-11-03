"""
AquaLens AI - Unit Test Suite for Objective 2 & Objective 3 Core Pipeline
Tests:
- 20-feature extractor ordering and robust error handling
- RF model inference consistency
- Source-specific baseline construction and sufficiency status
- Explainable anomaly detection and robust deviations
- Water Health Score transparency and data sufficiency
"""

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ml.feature_schema import FEATURE_NAMES
from backend.app.ml.feature_extractor import reconstruct_20_features, feature_dict_to_vector
from backend.app.ml.inference import get_inference_engine
from backend.app.db.session import Base
from backend.app.db.models import WaterSource, MonitoringStation, Observation, FeatureVector
from backend.app.services.fingerprint_service import FingerprintService
from backend.app.services.anomaly_service import AnomalyService
from backend.app.services.health_score_service import HealthScoreService
from backend.app.services.recommendation_service import RecommendationService


# In-memory SQLite database fixture for testing
@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_20_features_contract_and_order():
    """Verify all 20 features are extracted in the exact documented order and valid types."""
    assert len(FEATURE_NAMES) == 20
    test_img = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
    feats = reconstruct_20_features(test_img)

    assert len(feats) == 20
    assert list(feats.keys()) == FEATURE_NAMES
    for name, val in feats.items():
        assert isinstance(val, (float, int))
        assert np.isfinite(val)


def test_feature_extractor_rejection_of_invalid_images():
    """Verify corrupted, empty, or non-image inputs are rejected with clear errors."""
    with pytest.raises(ValueError, match="Input image is invalid"):
        reconstruct_20_features(None)

    with pytest.raises(ValueError, match="Input image is invalid"):
        reconstruct_20_features(np.array([]))

    with pytest.raises(ValueError, match="Expected a 3-channel BGR image"):
        reconstruct_20_features(np.zeros((100, 100), dtype=np.uint8))


def test_random_forest_inference_engine():
    """Verify the trained Random Forest classifier produces expected classes and structure."""
    engine = get_inference_engine()
    assert engine.is_loaded, f"Model failed to load: {engine.load_error}"
    assert set(engine.classes_) == {"High", "Low", "Medium"}

    test_img = np.ones((256, 256, 3), dtype=np.uint8) * 128
    feats = reconstruct_20_features(test_img)
    result = engine.classify_dict(feats)

    assert result["predicted_condition"] in engine.classes_
    assert set(result["raw_probabilities"].keys()) == {"High", "Low", "Medium"}
    assert "disclaimer" in result


def test_fingerprint_insufficient_data_status(test_db):
    """Verify that fewer than the minimum observations returns 'insufficient_data' status."""
    source = WaterSource(source_code="SRC-1", name="River A", source_type="River", region="North")
    test_db.add(source)
    test_db.flush()

    station = MonitoringStation(source_id=source.id, station_code="ST-1", name="Station 1", active=True)
    test_db.add(station)
    test_db.commit()

    # Create only 2 observations (threshold is 5)
    for i in range(2):
        obs = Observation(
            station_id=station.id,
            image_path=f"/test/img_{i}.jpg",
            is_eligible_for_baseline=True,
        )
        test_db.add(obs)
        test_db.flush()

        dummy_feats = {f: float(i + 1) for f in FEATURE_NAMES}
        fv = FeatureVector(observation_id=obs.id, features_json=str(dummy_feats).replace("'", '"'))
        test_db.add(fv)
    test_db.commit()

    baseline = FingerprintService.build_or_update_baseline(test_db, station.id, min_samples=5)
    assert baseline.status == "insufficient_data"
    assert baseline.sample_count == 2
    assert "minimum of 5" in baseline.notes


def test_fingerprint_established_baseline_and_anomaly_detection(test_db):
    """Verify that >= 5 observations constructs an established baseline with robust stats."""
    source = WaterSource(source_code="SRC-2", name="Lake B", source_type="Lake", region="East")
    test_db.add(source)
    test_db.flush()

    station = MonitoringStation(source_id=source.id, station_code="ST-2", name="Station 2", active=True)
    test_db.add(station)
    test_db.flush()

    # Create 6 observations with controlled feature values
    for i in range(6):
        obs = Observation(
            station_id=station.id,
            image_path=f"/test/img_{i}.jpg",
            is_eligible_for_baseline=True,
        )
        test_db.add(obs)
        test_db.flush()

        # Medians will be around 10.0, texture around 100.0
        dummy_feats = {f: 10.0 + (i * 0.1) for f in FEATURE_NAMES}
        dummy_feats["texture_intensity_variance"] = 100.0 + (i * 1.0)
        fv = FeatureVector(observation_id=obs.id, features_json=str(dummy_feats).replace("'", '"'))
        test_db.add(fv)
    test_db.commit()

    baseline = FingerprintService.build_or_update_baseline(test_db, station.id, min_samples=5)
    assert baseline.status == "established"
    assert baseline.sample_count == 6
    stats = baseline.get_stats()
    assert "texture_intensity_variance" in stats
    assert stats["texture_intensity_variance"]["median"] > 0

    # Test normal observation against established baseline
    normal_obs = Observation(
        station_id=station.id,
        image_path="/test/normal.jpg",
        is_eligible_for_baseline=True,
    )
    test_db.add(normal_obs)
    test_db.flush()
    normal_feats = {f: 10.1 for f in FEATURE_NAMES}
    normal_feats["texture_intensity_variance"] = 102.0
    test_db.add(FeatureVector(observation_id=normal_obs.id, features_json=str(normal_feats).replace("'", '"')))
    test_db.commit()

    anomaly_res = AnomalyService.save_or_update_anomaly(test_db, normal_obs, baseline)
    assert anomaly_res.status == "normal_variation"

    health = HealthScoreService.save_or_update_score(test_db, normal_obs, anomaly_res, baseline)
    assert health.status in ["provisional", "validated"]
    assert health.score is not None
    assert health.score >= 70.0  # Near baseline median

    # Test anomalous observation with massive texture spike
    anom_obs = Observation(
        station_id=station.id,
        image_path="/test/anom.jpg",
        is_eligible_for_baseline=True,
    )
    test_db.add(anom_obs)
    test_db.flush()
    anom_feats = {f: 10.1 for f in FEATURE_NAMES}
    anom_feats["texture_intensity_variance"] = 5000.0  # 50x jump
    anom_feats["colour_cast_blue_red"] = 150.0
    test_db.add(FeatureVector(observation_id=anom_obs.id, features_json=str(anom_feats).replace("'", '"')))
    test_db.commit()

    anom_result = AnomalyService.save_or_update_anomaly(test_db, anom_obs, baseline)
    assert anom_result.status in ["potential_anomaly", "persistent_anomaly"]
    assert "texture_intensity_variance" in anom_result.get_top_contributors()

    # Recommendations
    recs = RecommendationService.generate_recommendations_for_observation(test_db, anom_obs)
    assert len(recs) > 0
    categories = [r.category for r in recs]
    assert "AcquisitionCheck" in categories or "LaboratoryVerification" in categories
