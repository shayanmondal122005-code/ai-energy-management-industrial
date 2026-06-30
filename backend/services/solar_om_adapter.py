"""Solar O&M detection adapter — runs the vendored detection core on EMS data.

Bridges the EMS async/ORM world to the pure detection core (`backend/services/solar_om`,
vendored from the solar-om-detection repo). It loads a facility's recent solar readings,
attaches modeled irradiance + forecast SERVER-SIDE (no site sensor), runs the detectors
through the environmental gate, and returns alerts (₹/day) + health for the dashboard.

EMS readings are PLANT-LEVEL (one solar_kw per timestamp), so this runs the plant/
inverter-level detection (generation dip vs satellite-expected, outage, soiling). The
per-string + safety detectors light up automatically once an inverter gateway feeds
per-string telemetry into `readings`.
"""
from __future__ import annotations

import statistics
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.facilities_repo import FacilitiesRepository
from backend.repositories.readings_repo import ReadingsRepository
from backend.services.alert_service import INDIA_TARIFFS
from backend.services.solar_om.detectors.base import InMemoryAlertStore
from backend.services.solar_om.engine import IntradayConfig, run_intraday, site_health
from backend.services.solar_om.environment import (
    OpenMeteoSatelliteProvider,
    SatelliteSource,
)
from backend.services.solar_om.forecast import OpenMeteoForecast
from backend.services.solar_om.models import Inverter, Plant, Reading
from backend.services.solar_om.tariff import Tariff

# Uncalibrated default system efficiency. Slope-based (soiling) and ~0-power (outage)
# detectors don't depend on it; only the absolute-shortfall ones do, and their thresholds
# (≥15%) absorb this. Replaced by a real fit once calibration history is wired.
DEFAULT_ETA_BOS = 0.80


def _interval_hours(timestamps: list) -> float:
    deltas = [(timestamps[i + 1] - timestamps[i]).total_seconds() / 3600
              for i in range(len(timestamps) - 1)]
    return round(statistics.median(deltas), 4) if deltas else 0.25


def _serialize(alert: dict) -> dict:
    out = {}
    for k, v in alert.items():
        if hasattr(v, "value"):           # Severity / AlertStatus str-enums
            out[k] = v.value
        elif hasattr(v, "isoformat"):     # datetimes
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


async def run_om_detection(db: AsyncSession, facility_id: UUID, *, hours: int = 48) -> dict:
    """Run remote O&M detection for a facility and return a dashboard-ready payload."""
    fac = await FacilitiesRepository(db).get(facility_id)
    if fac is None:
        return {"facility_id": str(facility_id), "status": "facility_not_found"}

    readings = await ReadingsRepository(db).get_recent_raw(facility_id, hours=hours)
    rows = [r for r in readings if r.solar_kw is not None]
    if len(rows) < 4:
        return {"facility_id": str(facility_id), "status": "insufficient_data",
                "open_alerts": 0, "total_rupee_impact_per_day": 0.0, "alerts": []}

    plant = Plant(
        id=str(facility_id), name=fac.name, lat=fac.lat, lon=fac.lon,
        tilt_deg=abs(fac.lat), azimuth_deg=180.0,           # tilt≈latitude, due south
        rated_capacity_kwp=float(fac.solar_kw), eta_bos=DEFAULT_ETA_BOS)
    inverters = [Inverter(id="PLANT", plant_id=plant.id, rated_kw=float(fac.solar_kw),
                          modbus_slave_id=1)]
    intervals = [[Reading(ts=r.timestamp, inverter_id="PLANT", string_id=None,
                          ac_power_w=float(r.solar_kw) * 1000.0)] for r in rows]
    timestamps = [r.timestamp for r in rows]

    env = SatelliteSource(OpenMeteoSatelliteProvider())     # low-latency modeled POA
    forecast = OpenMeteoForecast().get(plant, timestamps[0], 24)
    tcfg = INDIA_TARIFFS.get(fac.state_tariff, INDIA_TARIFFS["West Bengal - CESC"])
    tariff = Tariff.flat(float(tcfg["normal"]))

    store = InMemoryAlertStore()
    try:
        run_intraday(plant, inverters, [], intervals, env, forecast, tariff, store,
                     cfg=IntradayConfig(interval_hours=_interval_hours(timestamps)))
    except Exception as exc:  # never let detection break the dashboard
        return {"facility_id": str(facility_id), "status": "error", "detail": str(exc),
                "open_alerts": 0, "total_rupee_impact_per_day": 0.0, "alerts": []}

    health = site_health(plant, store)
    return {
        "facility_id": str(facility_id),
        "status": "ok",
        "calibrated": False,                # uncalibrated estimate (eta_bos default)
        "expected_source": "open-meteo satellite POA → pvlib",
        "cloud_variability_index": forecast.cloud_variability_index,
        "clear_sky": forecast.clear_sky_flag,
        "open_alerts": health["open_alerts"],
        "total_rupee_impact_per_day": health["total_rupee_impact_per_day"],
        "suppressed": len(store.suppressed()),
        "alerts": [_serialize(a) for a in store.open_alerts()],
    }
