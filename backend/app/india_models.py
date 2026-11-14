"""India-only storage. Existing monitoring tables and RF artifacts are untouched."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from .db.session import Base
from .db.models import utc_now


class IndiaStation(Base):
    __tablename__ = 'india_stations'
    id = Column(Integer, primary_key=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class IndiaObservation(Base):
    __tablename__ = 'india_observations'
    __table_args__ = (UniqueConstraint('station_id', 'checksum'),)
    id = Column(Integer, primary_key=True)
    station_id = Column(Integer, ForeignKey('india_stations.id'), nullable=False, index=True)
    checksum = Column(String(64), nullable=False)
    filename = Column(String(100), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class IndiaRecord(Base):
    __tablename__ = 'india_records'
    id = Column(Integer, primary_key=True)
    station_id = Column(Integer, ForeignKey('india_stations.id'), nullable=False, index=True)
    kind = Column(String(24), nullable=False, index=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
