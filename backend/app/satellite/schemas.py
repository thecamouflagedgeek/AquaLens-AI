"""Request schemas for the satellite API (validation only)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AoiResolveRequest(BaseModel):
    """Resolve a location into a persisted AOI.

    Supply a GeoJSON ``geometry``, or a ``latitude``/``longitude`` point that will be
    buffered. A point without a buffer uses the configured default (300 m).
    """

    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True, extra="forbid")

    name: Optional[str] = Field(default=None, max_length=200)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    buffer_m: Optional[float] = None
    geometry: Optional[Dict[str, Any]] = None
    station_ref: Optional[str] = Field(default=None, max_length=120)
    country: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_location(self):
        has_point = self.latitude is not None and self.longitude is not None
        if self.geometry is None and not has_point:
            raise ValueError(
                "Provide a GeoJSON polygon, or both latitude and longitude for a buffered point."
            )
        if self.geometry is not None and (self.latitude is None) != (self.longitude is None):
            raise ValueError("Supply both latitude and longitude, or neither.")
        return self


class SatelliteFetchRequest(BaseModel):
    """Request historical satellite observations for an AOI.

    ``months`` applies only when explicit start/end months are omitted; the default
    window is the last 24 complete months.
    """

    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    start_month: Optional[str] = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_month: Optional[str] = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    months: Optional[int] = Field(default=None, ge=1, le=240)
    ndwi_threshold: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    max_cloud_pct: Optional[int] = Field(default=None, ge=0, le=100)
    force: bool = False

    @model_validator(mode="after")
    def require_window(self):
        if (self.start_month is None) != (self.end_month is None):
            raise ValueError("Provide both start_month and end_month, or neither.")
        if self.start_month and self.end_month and self.start_month > self.end_month:
            raise ValueError("start_month must be on or before end_month.")
        return self
