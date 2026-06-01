"""Optimization API — run LP dispatch optimizer for a facility."""
import logging
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import cache_get, cache_set
from backend.core.database import get_db
from backend.core.security import CurrentUser, get_current_user
from backend.repositories.readings_repo import ReadingsRepository
from backend.repositories.facilities_repo import FacilitiesRepository
from backend.services.forecasting import (
    add_time_features, predict_next_24h,
    readings_to_dataframe, train_load_model,
)
from backend.services.optimizer import optimize_dispatch
from backend.services.alert_service import INDIA_TARIFFS

logger = logging.getLogger(__name__)
router = APIRouter()


def _solar_forecast_24h(solar_kw: float, hour_now: int) -> list[float]:
    """Simple physics-based 24h solar forecast from current hour."""
    forecast = []
    for offset in range(24):
        h = (hour_now + offset) % 24
        if 6 <= h <= 18:
            angle = math.sin((h - 6) * math.pi / 12)
            # Monsoon cloud correction by month (simplified)
            from datetime import datetime, timezone
            month = datetime.now(timezone.utc).month
            cloud  = 0.45 if month in [6, 7, 8, 9] else 0.82
            forecast.append(round(max(0.0, solar_kw * angle * cloud), 1))
        else:
            forecast.append(0.0)
    return forecast


def _tariff_schedule_24h(state_tariff: str, hour_now: int) -> list[float]:
    """Return 24h tariff schedule starting from current hour."""
    tariff = INDIA_TARIFFS.get(state_tariff, INDIA_TARIFFS["West Bengal - CESC"])
    schedule = []
    for offset in range(24):
        h = (hour_now + offset) % 24
        if h in tariff["cheap_hours"]:
            schedule.append(tariff["cheap"])
        elif h in tariff["peak_hours"]:
            schedule.append(tariff["peak"])
        else:
            schedule.append(tariff["normal"])
    return schedule


@router.get("/{facility_id}/optimize")
async def run_optimizer(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Run LP optimizer for next 24 hours.
    Returns optimal battery charge/discharge schedule + savings.
    Cached 5 minutes — recalculates when cache expires or on demand.
    """
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    cache_key = f"optimizer:{facility_id}"
    cached    = await cache_get(cache_key)
    if cached:
        return cached

    # Load facility config
    fac_repo = FacilitiesRepository(db)
    facility = await fac_repo.get(facility_id)
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    # Get recent readings for load forecast
    r_repo   = ReadingsRepository(db)
    readings = await r_repo.get_recent_raw(facility_id, hours=240)

    if len(readings) < 48:
        raise HTTPException(
            status_code=422,
            detail=f"Need at least 48 hours of data to optimize. Have {len(readings)}.",
        )

    # Build load forecast
    df_raw = readings_to_dataframe(readings)
    df     = add_time_features(df_raw)
    model, mae, mape = train_load_model(df)
    fc     = predict_next_24h(model, df.tail(200))
    load_forecast = fc["forecast_kw"].tolist()

    # Build solar forecast and tariff schedule
    from datetime import datetime, timezone
    hour_now       = datetime.now(timezone.utc).hour
    solar_forecast = _solar_forecast_24h(facility.solar_kw, hour_now)
    tariff_schedule= _tariff_schedule_24h(facility.state_tariff, hour_now)

    # Current SoC from latest reading
    latest      = readings[-1]
    current_soc = float(getattr(latest, "battery_soc", 70)) / 100

    # Run LP optimizer
    schedule = optimize_dispatch(
        load_forecast=load_forecast,
        solar_forecast=solar_forecast,
        tariff_schedule=tariff_schedule,
        current_soc=current_soc,
        battery_kwh=facility.battery_kwh,
        max_charge_kw=150.0,
        max_discharge_kw=200.0,
    )

    result = {
        "facility_id"   : str(facility_id),
        "status"        : schedule.status,
        "cost_optimized": schedule.cost_optimized,
        "cost_baseline" : schedule.cost_baseline,
        "savings_today" : schedule.savings,
        "model_mae_kw"  : round(mae, 1),
        "model_mape_pct": round(mape, 1),
        "soc_trace"     : schedule.soc_trace,
        "min_soc_pct"   : min(schedule.soc_trace),
        "power_cut_risk": min(schedule.soc_trace) <= 12.0,
        "schedule"      : schedule.summary,
    }

    await cache_set(cache_key, result, ttl_seconds=300)

    # Store schedule in Redis for background job to read every 15 min
    await cache_set(
        f"dispatch_schedule:{facility_id}",
        {
            "charge_kw"   : schedule.charge_kw,
            "discharge_kw": schedule.discharge_kw,
            "grid_kw"     : schedule.grid_kw,
            "hour_base"   : hour_now,
        },
        ttl_seconds=86400,  # valid for 24 hours
    )

    return result
