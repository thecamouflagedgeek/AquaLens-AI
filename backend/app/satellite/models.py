"""Persistence for satellite AOIs, monthly observations and fetch jobs.

Kept strictly separate from ``db.models`` camera tables: no foreign keys into
``observations``/``feature_vectors``, and no satellite columns added to the 20-feature
contract. ``studio`` provenance is stored as an explicit ``station_ref`` string so a
satellite AOI can describe a river reach, lake or reservoir that has no camera station.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from ..db.models import utc_now
from ..db.session import Base


class SatelliteAOI(Base):
    """A named, reusable area of interest for satellite retrieval."""

    __tablename__ = "satellite_aois"

    id = Column(Integer, primary_key=True, index=True)
    aoi_key = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    kind = Column(String(32), nullable=False)                 # point_buffer | polygon
    latitude = Column(Float, nullable=True)                    # centre / centroid, WGS84
    longitude = Column(Float, nullable=True)
    buffer_m = Column(Float, nullable=True)                    # null for polygon AOIs
    geometry_geojson = Column(Text, nullable=False)            # WGS84 Polygon
    area_km2 = Column(Float, nullable=False)
    station_ref = Column(String(120), nullable=True, index=True)  # issuing UI/station reference
    country = Column(String(120), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    observations = relationship(
        "SatelliteObservation", back_populates="aoi", cascade="all, delete-orphan"
    )
    jobs = relationship(
        "SatelliteFetchJob", back_populates="aoi", cascade="all, delete-orphan"
    )


class SatelliteObservation(Base):
    """One satellite-derived monthly record for one AOI.

    Nullable measurements are intentional: a month with no usable imagery has no NDWI
    and no water area. ``status`` explains why, and the value is never coerced to zero.
    """

    __tablename__ = "satellite_observations"
    __table_args__ = (
        UniqueConstraint(
            "aoi_id",
            "month",
            "collection",
            "algorithm_version",
            "ndwi_threshold",
            "max_cloud_pct",
            name="uq_satellite_observation_identity",
        ),
        Index("ix_satellite_observations_aoi_month", "aoi_id", "month"),
    )

    id = Column(Integer, primary_key=True, index=True)
    aoi_id = Column(Integer, ForeignKey("satellite_aois.id"), nullable=False, index=True)
    month = Column(String(7), nullable=False)                  # YYYY-MM
    period_start = Column(String(10), nullable=False)          # inclusive ISO date
    period_end = Column(String(10), nullable=False)            # exclusive ISO date

    collection = Column(String(120), nullable=False)
    sensor = Column(String(32), nullable=True)                 # S2A/S2B/S2C composite
    resolution_m = Column(Float, nullable=True)

    ndwi_mean = Column(Float, nullable=True)
    ndwi_median = Column(Float, nullable=True)
    water_area_km2 = Column(Float, nullable=True)
    water_fraction = Column(Float, nullable=True)

    scene_count = Column(Integer, nullable=False, default=0)
    valid_pixel_count = Column(Integer, nullable=True)
    ndwi_threshold = Column(Float, nullable=False)
    max_cloud_pct = Column(Integer, nullable=False)

    status = Column(String(32), nullable=False)                # ok | no_scenes | no_valid_pixels | insufficient_pixels
    algorithm = Column(String(64), nullable=False)
    algorithm_version = Column(String(32), nullable=False)
    mask_rule = Column(String(200), nullable=True)
    quality_json = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    computed_at = Column(DateTime, default=utc_now, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    aoi = relationship("SatelliteAOI", back_populates="observations")


class SatelliteFetchJob(Base):
    """Persisted background fetch status; survives restarts and UI reloads."""

    __tablename__ = "satellite_fetch_jobs"
    __table_args__ = (Index("ix_satellite_fetch_jobs_aoi_status", "aoi_id", "status"),)

    id = Column(Integer, primary_key=True, index=True)
    aoi_id = Column(Integer, ForeignKey("satellite_aois.id"), nullable=False, index=True)

    status = Column(String(24), nullable=False, default="queued")   # queued|running|completed|failed
    start_month = Column(String(7), nullable=False)
    end_month = Column(String(7), nullable=False)
    ndwi_threshold = Column(Float, nullable=False)
    max_cloud_pct = Column(Integer, nullable=False)

    months_total = Column(Integer, nullable=False, default=0)
    months_completed = Column(Integer, nullable=False, default=0)
    months_skipped = Column(Integer, nullable=False, default=0)
    months_failed = Column(Integer, nullable=False, default=0)

    error = Column(Text, nullable=True)
    detail_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    aoi = relationship("SatelliteAOI", back_populates="jobs")


__all__ = ["SatelliteAOI", "SatelliteObservation", "SatelliteFetchJob"]
