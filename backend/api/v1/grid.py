"""Grid control API — mode switching, safety checks, load management.

All control commands follow a two-step pattern:
  1. POST /island  →  returns command_id + expires_at (60s window)
  2. POST /confirm →  confirms the command; backend executes

P1 loads (life safety) are physically blocked from shed in code.
All actions written to audit_log.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import cache_delete, cache_get, cache_set, key_grid_state, key_loads
from backend.core.database import get_db
from backend.core.rate_limit import limiter
from backend.core.security import CurrentUser, get_current_user
from backend.models.schemas import (
    CommandResponse,
    ConfirmCommandRequest,
    GridStateResponse,
    IslandRequest,
    LoadConfigResponse,
    LoadRestoreRequest,
    LoadShedRequest,
    ReconnectRequest,
)
from backend.repositories.grid_repo import GridRepository

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{facility_id}/grid/state", response_model=GridStateResponse)
async def get_grid_state(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    cached = await cache_get(key_grid_state(str(facility_id)))
    if cached:
        return GridStateResponse(**cached)

    repo  = GridRepository(db)
    state = await repo.get_state(facility_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Grid state not found — facility not configured")

    result = GridStateResponse.model_validate(state)
    await cache_set(key_grid_state(str(facility_id)), result.model_dump(mode="json"), ttl_seconds=10)
    return result


@router.post("/{facility_id}/grid/island", response_model=CommandResponse)
@limiter.limit("5/minute")
async def island(
    request: Request,
    facility_id: UUID,
    payload: IslandRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Step 1: Initiate islanding. Returns command_id for confirmation."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    current_user.require_operator()

    repo    = GridRepository(db)
    command = await repo.create_command(
        facility_id=facility_id,
        tenant_id=current_user.tenant_id,
        type="ISLAND",
        reason=payload.reason,
        priority=payload.priority,
        issued_by=current_user.user_id,
        issued_by_ip=request.client.host if request.client else None,
    )

    logger.info("GRID_ISLAND_INITIATED facility=%s command=%s user=%s", facility_id, command.id, current_user.user_id)

    return CommandResponse(
        command_id=command.id,
        type="ISLAND",
        status="pending_confirmation",
        expires_at=command.expires_at,
        message=f"Islanding command queued. Confirm within 60 seconds. Command ID: {command.id}",
    )


@router.post("/{facility_id}/grid/reconnect", response_model=CommandResponse)
@limiter.limit("5/minute")
async def reconnect(
    request: Request,
    facility_id: UUID,
    payload: ReconnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Step 1: Initiate grid reconnection with sync parameters."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    current_user.require_operator()

    # Validate sync window: voltage 220-240V, frequency 49.5-50.5Hz
    if not (215 <= payload.grid_voltage_v <= 245):
        raise HTTPException(status_code=400, detail=f"Grid voltage {payload.grid_voltage_v}V out of sync window (215-245V)")
    if not (49.5 <= payload.grid_frequency_hz <= 50.5):
        raise HTTPException(status_code=400, detail=f"Grid frequency {payload.grid_frequency_hz}Hz out of sync window (49.5-50.5Hz)")

    repo    = GridRepository(db)
    command = await repo.create_command(
        facility_id=facility_id,
        tenant_id=current_user.tenant_id,
        type="RECONNECT",
        reason=payload.reason,
        issued_by=current_user.user_id,
        issued_by_ip=request.client.host if request.client else None,
        value=payload.grid_voltage_v,
    )

    return CommandResponse(
        command_id=command.id,
        type="RECONNECT",
        status="pending_confirmation",
        expires_at=command.expires_at,
        message=f"Reconnect command queued. Grid: {payload.grid_voltage_v}V / {payload.grid_frequency_hz}Hz. Confirm within 60s.",
    )


@router.post("/{facility_id}/grid/confirm", response_model=CommandResponse)
@limiter.limit("5/minute")
async def confirm_command(
    request: Request,
    facility_id: UUID,
    payload: ConfirmCommandRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Step 2: Confirm a pending command. Executes immediately."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    current_user.require_operator()

    repo   = GridRepository(db)
    result = await repo.confirm_and_execute(payload.command_id, current_user.user_id)

    await cache_delete(key_grid_state(str(facility_id)))
    await cache_delete(key_loads(str(facility_id)))

    logger.info("COMMAND_EXECUTED command=%s type=%s result=%s user=%s",
                payload.command_id, result.type, result.result, current_user.user_id)

    return CommandResponse(
        command_id=result.id,
        type=result.type,
        status="executed" if result.result == "success" else "failed",
        expires_at=result.expires_at,
        message=result.error_message or f"{result.type} executed successfully.",
    )


@router.get("/{facility_id}/grid/loads", response_model=list[LoadConfigResponse])
async def get_loads(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")

    cache_key = key_loads(str(facility_id))
    cached    = await cache_get(cache_key)
    if cached is not None:
        return [LoadConfigResponse(**l) for l in cached]

    repo   = GridRepository(db)
    rows   = await repo.get_loads(facility_id)
    result = [LoadConfigResponse.model_validate(r) for r in rows]
    await cache_set(cache_key, [r.model_dump(mode="json") for r in result], ttl_seconds=20)
    return result


@router.post("/{facility_id}/grid/loads/shed", response_model=CommandResponse)
@limiter.limit("5/minute")
async def shed_load(
    request: Request,
    facility_id: UUID,
    payload: LoadShedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Shed a non-P1 load. P1 loads are blocked in code."""
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    current_user.require_operator()

    repo = GridRepository(db)
    load = await repo.get_load(facility_id, payload.load_id)

    if load is None:
        raise HTTPException(status_code=404, detail=f"Load {payload.load_id} not found")

    # P1 = life safety — physically cannot be shed
    if load.priority == 1:
        raise HTTPException(
            status_code=403,
            detail=f"Load {load.name} is Priority 1 (life safety) — cannot be shed under any circumstances",
        )

    command = await repo.create_command(
        facility_id=facility_id,
        tenant_id=current_user.tenant_id,
        type="LOAD_SHED",
        target=payload.load_id,
        reason=payload.reason,
        issued_by=current_user.user_id,
        issued_by_ip=request.client.host if request.client else None,
    )

    return CommandResponse(
        command_id=command.id,
        type="LOAD_SHED",
        status="pending_confirmation",
        expires_at=command.expires_at,
        message=f"Shed {load.name} ({load.rated_kw}kW, P{load.priority}). Confirm within 60s.",
    )


@router.get("/{facility_id}/grid/audit")
async def get_audit(
    facility_id: UUID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    repo = GridRepository(db)
    return await repo.get_audit_log(facility_id, limit)
