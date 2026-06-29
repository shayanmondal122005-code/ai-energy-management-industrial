"""Alerts API — list alerts, acknowledge, solar health."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import cache_get, cache_set, key_solar_health
from backend.core.database import get_db
from backend.core.security import CurrentUser, get_current_user
from backend.models.schemas import AcknowledgeAlertRequest, AlertResponse
from backend.repositories.alerts_repo import AlertsRepository
from backend.services.solar_health import run_solar_health

router = APIRouter()


@router.get("/{facility_id}/alerts", response_model=list[AlertResponse])
async def list_alerts(
    facility_id: UUID,
    severity: str | None = Query(default=None),
    unacknowledged_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    repo = AlertsRepository(db)
    return await repo.list_alerts(facility_id, severity, unacknowledged_only, limit)


@router.post("/{facility_id}/alerts/acknowledge")
async def acknowledge_alert(
    facility_id: UUID,
    payload: AcknowledgeAlertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    repo = AlertsRepository(db)
    await repo.acknowledge(payload.alert_id, current_user.user_id)
    return {"status": "acknowledged"}


@router.get("/{facility_id}/solar/health")
async def solar_health(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    cached = await cache_get(key_solar_health(str(facility_id)))
    if cached:
        return cached

    from backend.repositories.readings_repo import ReadingsRepository
    readings_repo = ReadingsRepository(db)
    readings      = await readings_repo.get_recent_raw(facility_id, hours=48)

    result = run_solar_health(readings)

    await cache_set(key_solar_health(str(facility_id)), result, ttl_seconds=300)
    return result


@router.get("/{facility_id}/solar/cleaning-roi")
async def solar_cleaning_roi(
    facility_id: UUID,
    cleaning_cost_rs: float = Query(2000.0, ge=0, description="Labour + water for one wash of this array"),
    days_since_clean: int = Query(0, ge=0, description="Days since the panels were last washed"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soiling-loss → cleaning-ROI: 'you've lost ₹X to dust; a wash costs ₹Y; clean now / wait'.

    Combines the measured Performance Ratio (solar-health) with today's generated kWh
    and the facility's self-consumption tariff rate to cost the soiling in rupees and
    recommend whether a wash pays back. Advisory only — it finds the loss; the operator acts.
    """
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    from dataclasses import asdict

    from backend.repositories.facilities_repo import FacilitiesRepository
    from backend.repositories.readings_repo import ReadingsRepository
    from backend.services.alert_service import INDIA_TARIFFS
    from backend.services.solar_cleaning_roi import cleaning_advice

    facility = await FacilitiesRepository(db).get(facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")

    readings_repo = ReadingsRepository(db)
    readings = await readings_repo.get_recent_raw(facility_id, hours=48)
    health = run_solar_health(readings)
    pr_now = float(health.get("performance_ratio", 1.0))

    gen = await readings_repo.get_solar_generation(facility_id)

    # Self-consumption value = the normal grid rate the solar offsets (not peak — no overclaim).
    tariff = INDIA_TARIFFS.get(facility.state_tariff, INDIA_TARIFFS["West Bengal - CESC"])
    solar_value_per_kwh = float(tariff["normal"])

    advice = cleaning_advice(
        measured_today_kwh=gen.today_kwh,
        pr_now=pr_now,
        solar_value_per_kwh=solar_value_per_kwh,
        cleaning_cost_rs=cleaning_cost_rs,
        days_since_clean=days_since_clean,
    )
    return {
        "facility_id": str(facility_id),
        "today_kwh": gen.today_kwh,
        "solar_value_per_kwh": solar_value_per_kwh,
        **asdict(advice),
    }
