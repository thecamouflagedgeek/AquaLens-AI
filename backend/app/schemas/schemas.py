"""
AquaLens AI - Pydantic Request & Response Schemas
Provides strict validation, serialization, and OpenAPI documentation types.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Auth & User Schemas
# ============================================================

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: Optional[str] = "viewer"


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Sources & Monitoring Stations Schemas
# ============================================================

class WaterSourceBase(BaseModel):
    source_code: str
    name: str
    source_type: str
    region: str
    description: Optional[str] = None
    is_demo: bool = False


class WaterSourceCreate(WaterSourceBase):
    pass


class MonitoringStationBase(BaseModel):
    station_code: str
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation_m: Optional[float] = None
    active: bool = True
    is_demo: bool = False


class MonitoringStationCreate(MonitoringStationBase):
    source_id: int


class MonitoringStationOut(MonitoringStationBase):
    id: int
    source_id: int
    created_at: datetime
    latest_observation_time: Optional[datetime] = None
    latest_condition: Optional[str] = None
    baseline_status: Optional[str] = None
    health_score: Optional[float] = None
    anomaly_status: Optional[str] = None
    is_demo: bool = False

    model_config = ConfigDict(from_attributes=True)


class WaterSourceOut(WaterSourceBase):
    id: int
    created_at: datetime
    stations: List[MonitoringStationOut] = []
    is_demo: bool = False

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Observations & Features Schemas
# ============================================================

class FeatureVectorOut(BaseModel):
    schema_version: str
    features: Dict[str, float]


class ClassificationOut(BaseModel):
    predicted_condition: str
    probabilities: Dict[str, float]
    model_version: str
    probability_note: str
    disclaimer: str


class ObservationOut(BaseModel):
    id: int
    station_id: int
    sampling_timestamp: datetime
    image_url: str
    camera_model: Optional[str] = None
    illumination_condition: Optional[str] = None
    is_eligible_for_baseline: bool
    is_demo: bool = False
    features: Optional[Dict[str, float]] = None
    classification: Optional[ClassificationOut] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Baseline / Fingerprint Schemas
# ============================================================

class FeatureStat(BaseModel):
    median: float
    q25: float
    q75: float
    iqr: float
    mad: float
    min: float
    max: float


class BaselineBuildRequest(BaseModel):
    min_samples: Optional[int] = None
    notes: Optional[str] = None


class SourceBaselineOut(BaseModel):
    id: int
    station_id: int
    version: str
    status: str  # established, insufficient_data, archived
    sample_count: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    methodology: str
    stats: Dict[str, FeatureStat] = {}
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Anomaly Detection Schemas
# ============================================================

class FeatureDeviation(BaseModel):
    feature_name: str
    observed_value: float
    baseline_median: float
    baseline_mad: float
    robust_z_score: float
    is_deviated: bool


class AnomalyResultOut(BaseModel):
    observation_id: int
    baseline_id: Optional[int] = None
    overall_anomaly_score: Optional[float] = None
    status: str  # normal_variation, potential_anomaly, persistent_anomaly, unassessed
    threshold_used: Optional[float] = None
    methodology: str
    deviations: Dict[str, FeatureDeviation] = {}
    top_contributing_features: List[str] = []
    warnings: List[str] = []
    scientific_disclaimer: str

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Water Health Score Schemas
# ============================================================

class WaterHealthScoreOut(BaseModel):
    observation_id: int
    baseline_id: Optional[int] = None
    score: Optional[float] = None  # None if unavailable
    status: str  # validated, provisional, unavailable
    methodology_version: str
    explanation: str
    limitations: str
    observation_timestamp: datetime
    data_sufficiency_status: str
    predicted_condition: Optional[str] = None


# ============================================================
# Trends & Forecast Schemas
# ============================================================

class TrendPoint(BaseModel):
    observation_id: int
    timestamp: datetime
    predicted_condition: str
    health_score: Optional[float] = None
    anomaly_score: Optional[float] = None
    texture_intensity_variance: Optional[float] = None
    colour_cast_blue_red: Optional[float] = None
    largest_contour_area: Optional[float] = None


class HistoricalTrendsOut(BaseModel):
    station_id: int
    station_name: str
    total_observations: int
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None
    points: List[TrendPoint] = []
    summary: str


class ForecastPoint(BaseModel):
    date: str
    predicted_health_score: float
    uncertainty_lower: float
    uncertainty_upper: float


class ForecastOut(BaseModel):
    station_id: int
    status: str  # completed, insufficient_data
    method: str
    horizon_days: int
    forecast_points: List[ForecastPoint] = []
    validation_metrics: Dict[str, Any] = {}
    explanation: str


# ============================================================
# Recommendations Schemas
# ============================================================

class RecommendationOut(BaseModel):
    id: int
    station_id: int
    observation_id: Optional[int] = None
    category: str
    title: str
    description: str
    hypothesis: Optional[str] = None
    action_items: List[str] = []
    priority: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Laboratory Results Schemas
# ============================================================

class LaboratoryResultOut(BaseModel):
    id: int
    station_id: int
    sample_timestamp: datetime
    turbidity_ntu: Optional[float] = None
    ph: Optional[float] = None
    dissolved_oxygen_mg_l: Optional[float] = None
    tss_mg_l: Optional[float] = None
    conductivity_us_cm: Optional[float] = None
    lab_operator: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
