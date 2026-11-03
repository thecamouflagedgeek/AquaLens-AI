"""
AquaLens AI - Database Entity Models
Defines all logical schema entities for source-specific water monitoring,
fingerprints, observations, feature vectors, classifications, anomalies,
health scores, laboratory results, forecasts, and audit logging.
"""

from datetime import datetime, timezone
import json
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from .session import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(128), unique=True, index=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    role = Column(String(32), default="viewer", nullable=False)  # admin, officer, researcher, viewer
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class WaterSource(Base):
    __tablename__ = "water_sources"

    id = Column(Integer, primary_key=True, index=True)
    source_code = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    source_type = Column(String(64), nullable=False)  # River, Lake, Reservoir, Estuary, Coastal, Groundwater
    region = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    is_demo = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    stations = relationship("MonitoringStation", back_populates="source", cascade="all, delete-orphan")


class MonitoringStation(Base):
    __tablename__ = "monitoring_stations"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("water_sources.id"), nullable=False, index=True)
    station_code = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    elevation_m = Column(Float, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    source = relationship("WaterSource", back_populates="stations")
    observations = relationship("Observation", back_populates="station", cascade="all, delete-orphan")
    baselines = relationship("SourceBaseline", back_populates="station", cascade="all, delete-orphan")
    laboratory_results = relationship("LaboratoryResult", back_populates="station", cascade="all, delete-orphan")
    forecast_runs = relationship("ForecastRun", back_populates="station", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="station", cascade="all, delete-orphan")


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("monitoring_stations.id"), nullable=False, index=True)
    sampling_timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)
    image_path = Column(String(512), nullable=False)
    image_checksum = Column(String(64), nullable=True)
    camera_model = Column(String(128), nullable=True)
    illumination_condition = Column(String(64), nullable=True)  # DirectSun, Overcast, Shaded, Artificial
    is_eligible_for_baseline = Column(Boolean, default=True, nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    station = relationship("MonitoringStation", back_populates="observations")
    feature_vector = relationship("FeatureVector", back_populates="observation", uselist=False, cascade="all, delete-orphan")
    classification = relationship("Classification", back_populates="observation", uselist=False, cascade="all, delete-orphan")
    anomaly_result = relationship("AnomalyResult", back_populates="observation", uselist=False, cascade="all, delete-orphan")
    health_score = relationship("WaterHealthScore", back_populates="observation", uselist=False, cascade="all, delete-orphan")


class FeatureVector(Base):
    __tablename__ = "feature_vectors"

    id = Column(Integer, primary_key=True, index=True)
    observation_id = Column(Integer, ForeignKey("observations.id"), unique=True, nullable=False, index=True)
    schema_version = Column(String(32), default="20-features-v1.0", nullable=False)
    features_json = Column(Text, nullable=False)  # JSON representation of exact 20 features
    created_at = Column(DateTime, default=utc_now, nullable=False)

    observation = relationship("Observation", back_populates="feature_vector")

    def get_features(self):
        return json.loads(self.features_json)

    def set_features(self, feat_dict):
        self.features_json = json.dumps(feat_dict)


class Classification(Base):
    __tablename__ = "classifications"

    id = Column(Integer, primary_key=True, index=True)
    observation_id = Column(Integer, ForeignKey("observations.id"), unique=True, nullable=False, index=True)
    model_version = Column(String(64), nullable=False)
    predicted_condition = Column(String(32), nullable=False)  # Low, Medium, High
    probabilities_json = Column(Text, nullable=False)  # JSON raw probabilities
    created_at = Column(DateTime, default=utc_now, nullable=False)

    observation = relationship("Observation", back_populates="classification")

    def get_probabilities(self):
        return json.loads(self.probabilities_json)


class SourceBaseline(Base):
    __tablename__ = "source_baselines"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("monitoring_stations.id"), nullable=False, index=True)
    version = Column(String(32), default="v1.0.0", nullable=False)
    status = Column(String(32), nullable=False)  # established, insufficient_data, archived
    sample_count = Column(Integer, default=0, nullable=False)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    methodology = Column(String(128), default="robust-median-iqr-mad", nullable=False)
    stats_json = Column(Text, nullable=True)  # JSON dictionary of per-feature medians, IQRs, MADs
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    station = relationship("MonitoringStation", back_populates="baselines")
    anomalies = relationship("AnomalyResult", back_populates="baseline")
    health_scores = relationship("WaterHealthScore", back_populates="baseline")

    def get_stats(self):
        return json.loads(self.stats_json) if self.stats_json else {}


class AnomalyResult(Base):
    __tablename__ = "anomaly_results"

    id = Column(Integer, primary_key=True, index=True)
    observation_id = Column(Integer, ForeignKey("observations.id"), unique=True, nullable=False, index=True)
    baseline_id = Column(Integer, ForeignKey("source_baselines.id"), nullable=True, index=True)
    overall_anomaly_score = Column(Float, nullable=True)
    status = Column(String(32), nullable=False)  # normal_variation, potential_anomaly, persistent_anomaly, unassessed
    threshold_used = Column(Float, nullable=True)
    methodology = Column(String(128), nullable=False)
    deviations_json = Column(Text, nullable=True)  # JSON per-feature deviations
    top_contributors_json = Column(Text, nullable=True)  # JSON list of highest contributing features
    warnings_json = Column(Text, nullable=True)  # JSON list of QC / environmental warnings
    created_at = Column(DateTime, default=utc_now, nullable=False)

    observation = relationship("Observation", back_populates="anomaly_result")
    baseline = relationship("SourceBaseline", back_populates="anomalies")

    def get_deviations(self):
        return json.loads(self.deviations_json) if self.deviations_json else {}

    def get_top_contributors(self):
        return json.loads(self.top_contributors_json) if self.top_contributors_json else []

    def get_warnings(self):
        return json.loads(self.warnings_json) if self.warnings_json else []


class WaterHealthScore(Base):
    __tablename__ = "water_health_scores"

    id = Column(Integer, primary_key=True, index=True)
    observation_id = Column(Integer, ForeignKey("observations.id"), unique=True, nullable=False, index=True)
    baseline_id = Column(Integer, ForeignKey("source_baselines.id"), nullable=True, index=True)
    score = Column(Float, nullable=True)  # Nullable if unavailable
    status = Column(String(32), nullable=False)  # validated, provisional, unavailable
    methodology_version = Column(String(64), nullable=False)
    explanation = Column(Text, nullable=False)
    limitations = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    observation = relationship("Observation", back_populates="health_score")
    baseline = relationship("SourceBaseline", back_populates="health_scores")


class LaboratoryResult(Base):
    __tablename__ = "laboratory_results"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("monitoring_stations.id"), nullable=False, index=True)
    sample_timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)
    turbidity_ntu = Column(Float, nullable=True)
    ph = Column(Float, nullable=True)
    dissolved_oxygen_mg_l = Column(Float, nullable=True)
    tss_mg_l = Column(Float, nullable=True)
    conductivity_us_cm = Column(Float, nullable=True)
    lab_operator = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    station = relationship("MonitoringStation", back_populates="laboratory_results")


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("monitoring_stations.id"), nullable=False, index=True)
    run_timestamp = Column(DateTime, default=utc_now, nullable=False)
    method = Column(String(64), nullable=False)
    horizon_days = Column(Integer, default=7, nullable=False)
    status = Column(String(32), nullable=False)  # completed, insufficient_data
    predictions_json = Column(Text, nullable=True)
    metrics_json = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    station = relationship("MonitoringStation", back_populates="forecast_runs")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("monitoring_stations.id"), nullable=False, index=True)
    observation_id = Column(Integer, ForeignKey("observations.id"), nullable=True, index=True)
    category = Column(String(64), nullable=False)  # Acquisition, AnomalyInvestigation, LabVerification, QualityControl
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    hypothesis = Column(Text, nullable=True)
    action_items_json = Column(Text, nullable=True)  # JSON list of concrete steps
    priority = Column(String(32), default="medium", nullable=False)  # low, medium, high
    created_at = Column(DateTime, default=utc_now, nullable=False)

    station = relationship("MonitoringStation", back_populates="recommendations")

    def get_action_items(self):
        return json.loads(self.action_items_json) if self.action_items_json else []


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(64), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(Integer, nullable=True)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
