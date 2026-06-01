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
