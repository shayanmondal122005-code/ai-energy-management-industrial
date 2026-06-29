"""Readings API — ingest sensor data, query history, live status."""
import logging
from io import StringIO
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.rate_limit import limiter
from backend.core.security import CurrentUser, get_current_user
from backend.models.schemas import IngestResponse, LiveResponse, ReadingIngest, SolarGenerationResponse, StatsResponse
from backend.repositories.readings_repo import ReadingsRepository
from backend.core.cache import (
    cache_get, cache_set, cache_delete,
    key_history_csv, key_live, key_solar_generation,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{facility_id}/ingest", response_model=IngestResponse)
@limiter.limit("10/minute")
async def ingest(
    request: Request,
    facility_id: UUID,
    payload: ReadingIngest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Receive a sensor reading from an IoT gateway or feeder."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    repo  = ReadingsRepository(db)
    count = await repo.insert(facility_id, payload)

    # Invalidate caches that a new reading makes stale
    await cache_delete(key_history_csv(str(facility_id), 600))
    await cache_delete(key_history_csv(str(facility_id), 500))
    await cache_delete(key_live(str(facility_id)))
    await cache_delete(key_solar_generation(str(facility_id)))

    return IngestResponse(status="received", records=count, facility_id=facility_id)


@router.get("/{facility_id}/live", response_model=LiveResponse)
async def live(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the most recent sensor reading for a facility."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    cache_key = key_live(str(facility_id))
    cached    = await cache_get(cache_key)
    if cached:
        return LiveResponse(**cached)

    repo    = ReadingsRepository(db)
    reading = await repo.get_latest(facility_id)

    if reading is None:
        return LiveResponse(
            status="empty", timestamp=None,
            load_kw=0, solar_kw=0, battery_soc=0, battery_temp=28,
            grid_kw=0, net_kw=0, source="none",
        )
    result = LiveResponse(
        status="ok",
        timestamp=reading.timestamp,
        load_kw=reading.load_kw,
        solar_kw=reading.solar_kw,
        battery_soc=reading.battery_soc,
        battery_temp=reading.battery_temp or 28.0,
        grid_kw=reading.grid_kw or 0,
        net_kw=reading.net_kw or 0,
        source=reading.source,
    )
    # short TTL — feeder posts every couple minutes; invalidated on ingest anyway
    await cache_set(cache_key, result.model_dump(mode="json"), ttl_seconds=15)
    return result


@router.get("/{facility_id}/history/csv")
async def history_csv(
    facility_id: UUID,
    hours: int = Query(default=600, ge=1, le=8760),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return hourly-aggregated history as CSV (for dashboard charts)."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    cache_key = key_history_csv(str(facility_id), hours)
    cached    = await cache_get(cache_key)
    if cached:
        return Response(cached, media_type="text/csv")

    repo  = ReadingsRepository(db)
    rows  = await repo.get_history_hourly(facility_id, hours)

    if not rows:
        return Response("timestamp,load_kw,solar_kw,temp_c\n", media_type="text/csv")

    df = pd.DataFrame([
        {"timestamp": r.hour, "load_kw": r.load_kw_avg or 0,
         "solar_kw": r.solar_kw_avg or 0, "temp_c": 28.0}
        for r in rows
    ])
    csv_str = df.to_csv(index=False)

    await cache_set(cache_key, csv_str, ttl_seconds=120)
    return Response(csv_str, media_type="text/csv")


@router.get("/{facility_id}/solar/generation", response_model=SolarGenerationResponse)
async def solar_generation(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Daily / monthly / lifetime solar energy generated (kWh) — for ROI tracking."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    cache_key = key_solar_generation(str(facility_id))
    cached    = await cache_get(cache_key)
    if cached:
        return SolarGenerationResponse(**cached)

    repo   = ReadingsRepository(db)
    result = await repo.get_solar_generation(facility_id)
    await cache_set(cache_key, result.model_dump(mode="json"), ttl_seconds=45)
    return result


@router.get("/{facility_id}/solar/payback")
async def solar_payback(
    facility_id: UUID,
    system_cost_rs: float = Query(..., gt=0, description="Installed capex of the solar array (₹)"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Solar ROI / payback: how much of the array's capex it has earned back, and — at the
    recent run rate — the straight-line break-even ETA. The 'protect your investment' view.

    Value is the energy the panels self-consume, priced at the facility's NORMAL grid rate
    (the energy they offset) — measured generation only, no sunnier-future assumptions.
    """
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    from datetime import datetime, timedelta, timezone

    from backend.repositories.facilities_repo import FacilitiesRepository
    from backend.services.alert_service import INDIA_TARIFFS
    from backend.services.solar_roi import solar_payback as compute_payback

    facility = await FacilitiesRepository(db).get(facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")

    gen = await ReadingsRepository(db).get_solar_generation(facility_id)

    # Recent run rate for the ETA: this month's kWh spread over the days elapsed so far.
    ist = timezone(timedelta(hours=5, minutes=30))
    day_of_month = datetime.now(ist).day
    recent_daily_kwh = (gen.month_kwh / day_of_month) if day_of_month > 0 and gen.month_kwh > 0 else None

    tariff = INDIA_TARIFFS.get(facility.state_tariff, INDIA_TARIFFS["West Bengal - CESC"])
    solar_value_per_kwh = float(tariff["normal"])

    from dataclasses import asdict

    payback = compute_payback(
        total_kwh=gen.total_kwh,
        system_cost_rs=system_cost_rs,
        solar_value_per_kwh=solar_value_per_kwh,
        recent_daily_kwh=recent_daily_kwh,
    )
    return {
        "facility_id": str(facility_id),
        "solar_value_per_kwh": solar_value_per_kwh,
        "month_kwh": gen.month_kwh,
        **asdict(payback),
    }


@router.get("/{facility_id}/stats", response_model=StatsResponse)
async def stats(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Aggregate stats for a facility."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    repo = ReadingsRepository(db)
    s    = await repo.get_stats(facility_id)
    return s
