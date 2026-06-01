"""Safe mode — executes when watchdog detects any malfunction.

Priority:
  1. Keep grid connected (never island during fault)
  2. Put battery in HOLD (don't risk discharge into fault)
  3. Shed P4-P5 loads to conserve energy
  4. NEVER touch P1 loads (ICU, OT, life support)
  5. Pause optimizer until fault cleared

This function is called by the watchdog task immediately on detection.
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

logger = logging.getLogger(__name__)

# P1 is sacred — never shed these under any circumstances
PROTECTED_PRIORITIES = {1}

# Shed these first during safe mode
SHED_PRIORITIES = {5, 4}


async def activate_safe_mode(
    facility_id: UUID,
    tenant_id: UUID,
    malfunction_types: list[str],
    db,
) -> dict:
    """
    Immediately:
    1. Set grid_state → mode=GRID_CONNECTED, battery_command=HOLD
    2. Shed all P4 and P5 loads
    3. Write to audit_log
    4. Store safe_mode flag in Redis (pauses optimizer)
    """
    from sqlalchemy import select
    from backend.models.database import GridState, LoadConfig, AuditLog
    from backend.core.cache import cache_set

    actions_taken = []

    # ── Step 1: Force grid connected + battery HOLD ──────────
    result = await db.execute(
        select(GridState).where(GridState.facility_id == facility_id)
    )
    gs = result.scalar_one_or_none()
    if gs:
        prev_mode    = gs.mode
        prev_cmd     = gs.battery_command
        gs.mode              = "GRID_CONNECTED"
        gs.main_breaker      = True
        gs.battery_command   = "HOLD"
        gs.last_mode_change  = datetime.now(timezone.utc)
        actions_taken.append(f"Grid: {prev_mode} → GRID_CONNECTED")
        actions_taken.append(f"Battery: {prev_cmd} → HOLD")

    # ── Step 2: Shed P4 + P5 loads (never P1) ───────────────
    loads_result = await db.execute(
        select(LoadConfig).where(
            LoadConfig.facility_id == facility_id,
            LoadConfig.priority.in_(SHED_PRIORITIES),
            LoadConfig.is_on == True,
        )
    )
    shed_loads = list(loads_result.scalars().all())
    shed_kw    = 0.0

    for load in shed_loads:
        load.is_on  = False
        shed_kw    += load.rated_kw
        actions_taken.append(f"Shed P{load.priority} load: {load.name} ({load.rated_kw}kW)")

    # ── Step 3: Audit log entry ──────────────────────────────
    audit = AuditLog(
        facility_id = facility_id,
        tenant_id   = tenant_id,
        event       = "SAFE_MODE_ACTIVATED",
        data        = {
            "malfunctions": malfunction_types,
            "actions"     : actions_taken,
            "shed_kw"     : round(shed_kw, 1),
            "timestamp"   : datetime.now(timezone.utc).isoformat(),
        },
    )
    db.add(audit)
    await db.flush()

    # ── Step 4: Flag in Redis — pauses optimizer ─────────────
    await cache_set(
        f"safe_mode:{facility_id}",
        {
            "active"      : True,
            "since"       : datetime.now(timezone.utc).isoformat(),
            "malfunctions": malfunction_types,
        },
        ttl_seconds=3600,  # auto-clears after 1 hour if not renewed
    )

    logger.critical(
        "SAFE MODE ACTIVATED facility=%s shed_kw=%.0f faults=%s",
        facility_id, shed_kw, malfunction_types,
    )

    return {
        "activated"  : True,
        "shed_kw"    : round(shed_kw, 1),
        "shed_loads" : len(shed_loads),
        "actions"    : actions_taken,
    }


async def deactivate_safe_mode(facility_id: UUID, db) -> None:
    """Call when fault is cleared and operator confirms system healthy."""
    from backend.core.cache import cache_delete
    from sqlalchemy import select
    from backend.models.database import LoadConfig, AuditLog, GridState

    # Restore P4-P5 loads
    loads_result = await db.execute(
        select(LoadConfig).where(
            LoadConfig.facility_id == facility_id,
            LoadConfig.priority.in_(SHED_PRIORITIES),
            LoadConfig.is_on == False,
        )
    )
    for load in loads_result.scalars().all():
        load.is_on = True

    audit = AuditLog(
        facility_id=facility_id,
        event="SAFE_MODE_CLEARED",
        data={"timestamp": datetime.now(timezone.utc).isoformat()},
    )
    db.add(audit)
    await db.flush()

    await cache_delete(f"safe_mode:{facility_id}")
    logger.info("Safe mode cleared for facility=%s", facility_id)


async def is_safe_mode_active(facility_id: UUID) -> bool:
    """Check if safe mode is currently active for a facility."""
    from backend.core.cache import cache_get
    data = await cache_get(f"safe_mode:{facility_id}")
    return bool(data and data.get("active"))
