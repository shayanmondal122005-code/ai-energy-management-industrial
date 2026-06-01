"""Pydantic schemas — request/response contracts for all API endpoints."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Auth ────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    user_id: UUID
    tenant_id: UUID
    email: str
    role: str
    full_name: Optional[str]


# ── Readings ────────────────────────────────────────────────

class ReadingIngest(BaseModel):
    timestamp: datetime
    load_kw: float = Field(ge=0, le=10000)
    solar_kw: float = Field(ge=0, le=5000, default=0)
    battery_soc: float = Field(ge=0, le=100, default=0)
    battery_temp: Optional[float] = Field(ge=-10, le=80, default=None)
    grid_kw: float = Field(default=0)
    net_kw: float = Field(default=0)
    source: str = Field(default="iot_gateway")

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        allowed = {"iot_gateway", "feeder", "simulated", "manual"}
        if v not in allowed:
            raise ValueError(f"source must be one of {allowed}")
        return v


class ReadingResponse(BaseModel):
    id: UUID
    facility_id: UUID
    timestamp: datetime
    load_kw: float
    solar_kw: float
    battery_soc: float
    battery_temp: Optional[float]
    grid_kw: float
    net_kw: float
    source: str

    model_config = {"from_attributes": True}


class LiveResponse(BaseModel):
    status: str
    timestamp: Optional[datetime]
    load_kw: float
    solar_kw: float
    battery_soc: float
    battery_temp: float
    grid_kw: float
    net_kw: float
    source: str


class IngestResponse(BaseModel):
    status: str
    records: int
    facility_id: UUID


# ── Facilities ──────────────────────────────────────────────

class FacilityCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    city: str = Field(default="Kolkata")
    lat: float = Field(ge=-90, le=90, default=22.57)
    lon: float = Field(ge=-180, le=180, default=88.36)
    state_tariff: str = Field(default="West Bengal - CESC")
    battery_kwh: float = Field(gt=0, default=500)
    solar_kw: float = Field(ge=0, default=200)
    avg_load_kw: float = Field(gt=0, default=300)


class FacilityResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    city: str
    lat: float
    lon: float
    state_tariff: str
    battery_kwh: float
    solar_kw: float
    avg_load_kw: float
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Alerts ──────────────────────────────────────────────────

class AlertResponse(BaseModel):
    id: UUID
    facility_id: UUID
    severity: str
    type: str
    message: str
    value: Optional[float]
    threshold: Optional[float]
    whatsapp_sent: bool
    acknowledged_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class AcknowledgeAlertRequest(BaseModel):
    alert_id: UUID


# ── Grid control ────────────────────────────────────────────

class GridStateResponse(BaseModel):
    facility_id: UUID
    mode: str
    main_breaker: bool
    battery_command: str
    grid_voltage_v: Optional[float]
    grid_frequency_hz: Optional[float]
    last_mode_change: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IslandRequest(BaseModel):
    reason: str = Field(min_length=5)
    priority: str = Field(default="normal")


class ReconnectRequest(BaseModel):
    reason: str = Field(min_length=5)
    grid_voltage_v: float = Field(ge=200, le=260, description="Measured grid voltage before sync")
    grid_frequency_hz: float = Field(ge=48.0, le=52.0, description="Measured grid frequency before sync")


class ConfirmCommandRequest(BaseModel):
    command_id: UUID


class CommandResponse(BaseModel):
    command_id: UUID
    type: str
    status: str  # 'pending_confirmation' | 'confirmed' | 'executed' | 'expired'
    expires_at: datetime
    message: str


# ── Load management ─────────────────────────────────────────

class LoadShedRequest(BaseModel):
    load_id: str
    reason: str = Field(min_length=5)


class LoadRestoreRequest(BaseModel):
    load_id: str
    reason: str = Field(min_length=5)


class LoadConfigResponse(BaseModel):
    id: UUID
    load_id: str
    name: str
    priority: int
    rated_kw: float
    contactor_id: Optional[str]
    is_on: bool
    shed_order: Optional[int]

    model_config = {"from_attributes": True}


# ── Stats ───────────────────────────────────────────────────

class StatsResponse(BaseModel):
    facility_id: UUID
    avg_load_kw: float
    peak_load_kw: float
    avg_solar_kw: float
    total_readings: int
    data_from: Optional[datetime]
    data_to: Optional[datetime]


# ── Health ──────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str  # 'ok' | 'degraded' | 'down'
    version: str
    db: bool
    redis: bool
    timestamp: datetime
