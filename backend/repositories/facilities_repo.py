"""Facilities repository."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Facility
from backend.models.schemas import FacilityCreate


class FacilitiesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_tenant(self, tenant_id: UUID) -> list[Facility]:
        result = await self.db.execute(
            select(Facility)
            .where(Facility.tenant_id == tenant_id, Facility.is_active == True)
            .order_by(Facility.name)
        )
        return list(result.scalars().all())

    async def get(self, facility_id: UUID) -> Facility | None:
        result = await self.db.execute(
            select(Facility).where(Facility.id == facility_id, Facility.is_active == True)
        )
        return result.scalar_one_or_none()

    async def create(self, tenant_id: UUID, payload: FacilityCreate) -> Facility:
        facility = Facility(tenant_id=tenant_id, **payload.model_dump())
        self.db.add(facility)
        await self.db.flush()
        await self.db.refresh(facility)
        return facility

    async def deactivate(self, facility_id: UUID, tenant_id: UUID) -> None:
        result = await self.db.execute(
            select(Facility).where(Facility.id == facility_id, Facility.tenant_id == tenant_id)
        )
        facility = result.scalar_one_or_none()
        if facility:
            facility.is_active = False
            await self.db.flush()
