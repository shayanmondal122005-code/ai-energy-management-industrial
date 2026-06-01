"""Auth API — login, refresh, logout, me."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.rate_limit import limiter
from backend.core.security import (
    CurrentUser,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    verify_password,
)
from backend.models.schemas import LoginRequest, MeResponse, RefreshRequest, TokenResponse
from backend.repositories.users_repo import UsersRepository

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = UsersRepository(db)
    user = await repo.get_by_email(payload.email)

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Password verified against Supabase Auth hash stored in users table
    if not verify_password(payload.password, user.password_hash or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    facility_ids = await repo.get_facility_ids(user.id, user.tenant_id)

    access_token  = create_access_token(user.id, user.tenant_id, user.role, facility_ids)
    refresh_token = create_refresh_token(user.id, user.tenant_id)

    await repo.update_last_login(user.id)

    logger.info("LOGIN user_id=%s role=%s", user.id, user.role)

    from backend.core.config import get_settings
    settings = get_settings()
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    decoded = decode_token(payload.refresh_token)
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    from uuid import UUID
    user_id   = UUID(decoded["sub"])
    tenant_id = UUID(decoded["tenant_id"])

    repo         = UsersRepository(db)
    user         = await repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    facility_ids  = await repo.get_facility_ids(user_id, tenant_id)
    access_token  = create_access_token(user_id, tenant_id, user.role, facility_ids)
    refresh_token = create_refresh_token(user_id, tenant_id)

    from backend.core.config import get_settings
    settings = get_settings()
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)):
    return MeResponse(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        email="",  # fetched from DB if needed
        role=current_user.role,
        full_name=None,
    )
