from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from backend.core.config import get_settings

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


# ── Token creation ──────────────────────────────────────────

def create_access_token(
    user_id: UUID,
    tenant_id: UUID,
    role: str,
    facility_ids: list[str],
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "facility_ids": facility_ids,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID, tenant_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ── Token verification ──────────────────────────────────────

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── FastAPI dependencies ────────────────────────────────────

class CurrentUser:
    def __init__(self, user_id: UUID, tenant_id: UUID, role: str, facility_ids: list[str]):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role
        self.facility_ids = facility_ids

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"

    def can_access_facility(self, facility_id: UUID) -> bool:
        if self.is_super_admin:
            return True
        return str(facility_id) in self.facility_ids

    def require_operator(self):
        if self.role not in ("operator", "tenant_admin", "super_admin"):
            raise HTTPException(status_code=403, detail="Operator role required")

    def require_admin(self):
        if self.role not in ("tenant_admin", "super_admin"):
            raise HTTPException(status_code=403, detail="Admin role required")

    def require_super_admin(self):
        if self.role != "super_admin":
            raise HTTPException(status_code=403, detail="Super admin role required")


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return CurrentUser(
        user_id=UUID(payload["sub"]),
        tenant_id=UUID(payload["tenant_id"]),
        role=payload["role"],
        facility_ids=payload.get("facility_ids", []),
    )


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> Optional[CurrentUser]:
    if credentials is None:
        return None
    try:
        return get_current_user(credentials)
    except HTTPException:
        return None


# ── Password hashing ────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── API key hashing ─────────────────────────────────────────

def hash_api_key(key: str) -> str:
    return bcrypt.hashpw(key.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_api_key(key: str, hashed: str) -> bool:
    return bcrypt.checkpw(key.encode(), hashed.encode())
