"""Forecast API — 24h AI load + solar + SoC forecast per facility."""
import logging
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import cache_get, cache_set
from backend.core.database import get_db
from backend.core.security import CurrentUser, get_current_user
from backend.repositories.readings_repo import ReadingsRepository
from backend.services.battery_tracker import BatteryTracker
from backend.services.forecasting import (
    add_time_features,
    predict_next_24h,
    readings_to_dataframe,
    train_load_model,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{facility_id}/forecast/24h")
async def forecast_24h(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate 24h AI load forecast with SoC projection."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    cache_key = f"forecast:{facility_id}"
    cached    = await cache_get(cache_key)
    if cached:
        return cached

    repo     = ReadingsRepository(db)
    readings = await repo.get_recent_raw(facility_id, hours=240)

    if len(readings) < 48:
        raise HTTPException(
            status_code=422,
            detail=f"Need at least 48 hours of readings. Have {len(readings)}.",
        )

    df_raw = readings_to_dataframe(readings)
    df     = add_time_features(df_raw)

    try:
        model, mae, mape = train_load_model(df)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    forecast = predict_next_24h(model, df.tail(200))

    latest  = readings[-1]
    battery = BatteryTracker()
    battery.soc = float(getattr(latest, "battery_soc", 70)) / 100

    solar_fc  = [
        max(0.0, 200 * math.sin((h % 24 - 6) * math.pi / 12) * 0.82)
        if 6 <= (h % 24) <= 18 else 0.0
        for h in range(24)
    ]
    soc_trace = battery.simulate_future(forecast["forecast_kw"].tolist(), solar_fc)

    result = {
        "facility_id": str(facility_id),
        "mae_kw"     : round(mae, 1),
        "mape_pct"   : round(mape, 1),
        "accuracy_pct": round(max(0, 100 - mape), 1),
        "forecast"   : [
            {
                "timestamp"  : str(ts),
                "forecast_kw": float(row["forecast_kw"]),
                "solar_kw"   : solar_fc[i],
                "soc_pct"    : soc_trace[i + 1],
            }
            for i, (ts, row) in enumerate(forecast.iterrows())
        ],
    }

    await cache_set(cache_key, result, ttl_seconds=300)
    return result
