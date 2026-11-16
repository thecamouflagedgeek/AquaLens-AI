"""Non-destructive schema setup for the satellite tables.

The repository has no migration framework: ``Base.metadata.create_all`` in the
FastAPI lifespan hook is the only schema mechanism, and it is additive. This module
follows that convention but is explicit and scoped, so the satellite tables can be
created on an existing database without touching, recreating or clearing any table that
already holds camera, India or laboratory data.
"""

from __future__ import annotations

from typing import List

from sqlalchemy.engine import Engine

from ..db.session import Base, engine as default_engine
from .models import SatelliteAOI, SatelliteFetchJob, SatelliteObservation

SATELLITE_TABLES = (SatelliteAOI.__table__, SatelliteObservation.__table__, SatelliteFetchJob.__table__)


def ensure_satellite_schema(bind: Engine | None = None) -> List[str]:
    """Create only the satellite tables if they are missing. Returns created names."""
    target = bind or default_engine
    with target.connect() as connection:
        existing = set(target.dialect.get_table_names(connection))
    created = [table.name for table in SATELLITE_TABLES if table.name not in existing]
    Base.metadata.create_all(bind=target, tables=list(SATELLITE_TABLES), checkfirst=True)
    return created
