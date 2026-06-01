"""Safety API — safe mode status, manual clear, watchdog status."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import CurrentUser, get_current_user
from backend.repositories.readings_repo import ReadingsRepository
from backend.services.watchdog import run_watchdog
from backend.services.safe_mode import (
    activate_safe_mode,
    deactivate_safe_mode,
    is_safe_mode_active,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{facility_id}/safety/status")
async def safety_status(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Returns current watchdog status for a facility.
    Runs a live check against latest readings — not cached.
    """
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    from backend.repositories.facilities_repo import FacilitiesRepository
    fac_repo = FacilitiesRepository(db)
    facility = await fac_repo.get(facility_id)
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    r_repo   = ReadingsRepository(db)
    readings = await r_repo.get_recent_raw(facility_id, hours=1)

    result     = run_watchdog(
        readings=readings,
        facility_name=facility.name,
        facility_id=str(facility_id),
        solar_kw_installed=facility.solar_kw,
    )
    safe_mode = await is_safe_mode_active(facility_id)

    return {
        "facility_id"       : str(facility_id),
        "safe"              : result.safe,
        "safe_mode_active"  : safe_mode,
        "malfunction_count" : len(result.malfunctions),
        "malfunctions"      : [
            {
                "type"        : m.type.value,
                "severity"    : m.severity,
                "message"     : m.message,
                "value"       : m.value,
                "threshold"   : m.threshold,
                "action_taken": m.action_taken,
            }
            for m in result.malfunctions
        ],
        "data_age_readings" : len(readings),
    }


@router.post("/{facility_id}/safety/clear")
async def clear_safe_mode(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Manually clear safe mode after fault is resolved.
    Requires operator role — logged in audit trail.
    """
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    current_user.require_operator()

    await deactivate_safe_mode(facility_id, db)
    await db.commit()

    logger.info("Safe mode cleared by user=%s for facility=%s", current_user.user_id, facility_id)
    return {"status": "cleared", "message": "Safe mode deactivated. Optimizer will resume on next cycle."}
