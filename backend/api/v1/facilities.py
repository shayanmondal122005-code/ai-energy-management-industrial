"""Facilities API — CRUD for customer facilities."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import cache_get, cache_set, cache_delete, key_facilities
from backend.core.database import get_db
from backend.core.security import CurrentUser, get_current_user
from backend.models.schemas import FacilityCreate, FacilityResponse
from backend.repositories.facilities_repo import FacilitiesRepository

router = APIRouter()


@router.get("/", response_model=list[FacilityResponse])
async def list_facilities(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    cache_key = key_facilities(str(current_user.tenant_id))
    cached    = await cache_get(cache_key)
    if cached is not None:
        return [FacilityResponse(**f) for f in cached]

    repo    = FacilitiesRepository(db)
    rows    = await repo.list_for_tenant(current_user.tenant_id)
    result  = [FacilityResponse.model_validate(r) for r in rows]
    await cache_set(cache_key, [r.model_dump(mode="json") for r in result], ttl_seconds=30)
    return result


@router.post("/", response_model=FacilityResponse, status_code=201)
async def create_facility(
    payload: FacilityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    current_user.require_admin()
    repo = FacilitiesRepository(db)
    facility = await repo.create(current_user.tenant_id, payload)
    await cache_delete(key_facilities(str(current_user.tenant_id)))
    return facility


@router.get("/{facility_id}", response_model=FacilityResponse)
async def get_facility(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.can_access_facility(facility_id):
        raise HTTPException(status_code=403, detail="Access denied")
    repo     = FacilitiesRepository(db)
    facility = await repo.get(facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    return facility


@router.delete("/{facility_id}", status_code=204)
async def delete_facility(
    facility_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    current_user.require_admin()
    repo = FacilitiesRepository(db)
    await repo.deactivate(facility_id, current_user.tenant_id)
    await cache_delete(key_facilities(str(current_user.tenant_id)))
