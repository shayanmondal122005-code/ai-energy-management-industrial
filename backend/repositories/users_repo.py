"""Users repository."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Facility, Tenant, User


class UsersRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tenant_and_user(
        self,
        email: str,
        password_hash: str,
        full_name: str,
        organization: str,
    ) -> User:
        """Create a new tenant + owner user in one transaction."""
        tenant = Tenant(id=uuid4(), name=organization, plan="starter", is_active=True)
        self.db.add(tenant)
        await self.db.flush()  # get tenant.id

        user = User(
            id=uuid4(),
            tenant_id=tenant.id,
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            role="tenant_admin",
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_facility_ids(self, user_id: UUID, tenant_id: UUID) -> list[str]:
        """Return facility IDs accessible to this user."""
        result = await self.db.execute(
            select(Facility.id).where(Facility.tenant_id == tenant_id, Facility.is_active == True)
        )
        return [str(row) for row in result.scalars().all()]

    async def update_last_login(self, user_id: UUID) -> None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.last_login_at = datetime.now(timezone.utc)
            await self.db.flush()
