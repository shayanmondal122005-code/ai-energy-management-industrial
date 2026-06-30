"""Pure domain model — framework-free dataclasses shared by every detector.

These deliberately import NOTHING from FastAPI/SQLModel/Redis so the detection
brain unit-tests without a database or web server. The DB layer (app/db) maps its
SQLModel rows to/from these; the API layer never reaches past them into ORM rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    INVESTIGATE = "investigate"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    OPEN = "open"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class EnvSource(str, Enum):
    SATELLITE = "satellite"
    FORECAST = "forecast"
    SENSOR = "sensor"


# ── Static plant configuration ───────────────────────────────────────────────
@dataclass(frozen=True)
class Plant:
    id: str
    name: str
    lat: float
    lon: float
    tilt_deg: float
    azimuth_deg: float                 # 180 = due south (northern hemisphere)
    rated_capacity_kwp: float
    module_temp_coeff: float = -0.0035  # gamma_P, per °C (Pmax)
    noct_c: float = 45.0
    eta_bos: float | None = None        # calibrated; None => uncalibrated => suppress
    tariff_id: str | None = None
    commissioned_at: datetime | None = None
    baseline_pr: float | None = None

    @property
    def calibrated(self) -> bool:
        return self.eta_bos is not None


@dataclass(frozen=True)
class Inverter:
    id: str
    plant_id: str
    rated_kw: float
    modbus_slave_id: int = 1
    vendor: str = ""
    model: str = ""
    clipping_kw: float | None = None
    riso_threshold_kohm: float | None = None  # vendor default trip threshold


@dataclass(frozen=True)
class StringSpec:
    id: str
    inverter_id: str
    mppt_index: int
    rated_share_fraction: float          # this string's share of inverter nameplate


# ── Time-series ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Reading:
    ts: datetime
    inverter_id: str
    string_id: str | None = None
    dc_voltage: float | None = None
    dc_current: float | None = None
    ac_power_w: float | None = None
    energy_kwh_cumulative: float | None = None
    inverter_temp_c: float | None = None
    status_code: int | None = None
    fault_codes: list = field(default_factory=list)
    riso_kohm: float | None = None
    ground_fault: bool | None = None
    arc_fault: bool | None = None


@dataclass(frozen=True)
class EnvSample:
    ts: datetime
    plant_id: str
    poa_wm2: float
    ambient_temp_c: float
    ghi_wm2: float
    source: EnvSource = EnvSource.SATELLITE
    cloud_variability_index: float | None = None
    clear_sky_flag: bool | None = None


@dataclass(frozen=True)
class ForecastWindow:
    """A look-ahead window from our EMS forecast service."""
    plant_id: str
    ts_start: datetime
    poa_forecast_wm2: list[float]
    cloud_variability_index: float       # 0 = dead clear, 1 = highly broken cloud
    clear_sky_flag: bool


# ── Detector output ──────────────────────────────────────────────────────────
@dataclass
class AlertDraft:
    """A detector's proposed alert. The AlertStore reconciles drafts with open
    rows (open / update / close) — drafts themselves carry no DB identity."""
    plant_id: str
    type: str
    severity: Severity
    recommended_action: str
    confidence: float = 1.0
    inverter_id: str | None = None
    string_id: str | None = None
    rupee_impact_per_day: float | None = None
    rupee_accumulated: float | None = None
    risk_note: str | None = None
    evidence: dict = field(default_factory=dict)
    status: AlertStatus = AlertStatus.OPEN

    @property
    def dedup_key(self) -> tuple:
        """Identity for idempotent open/update — one open alert per (scope, type)."""
        return (self.plant_id, self.inverter_id, self.string_id, self.type)
