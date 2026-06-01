"""Alerts repository."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Alert


class AlertsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_alerts(
        self,
        facility_id: UUID,
        severity: str | None = None,
        unacknowledged_only: bool = False,
        limit: int = 50,
    ) -> list[Alert]:
        q = select(Alert).where(Alert.facility_id == facility_id)
        if severity:
            q = q.where(Alert.severity == severity)
        if unacknowledged_only:
            q = q.where(Alert.acknowledged_at.is_(None))
        q = q.order_by(Alert.created_at.desc()).limit(limit)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def acknowledge(self, alert_id: UUID, user_id: UUID) -> None:
        result = await self.db.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one_or_none()
        if alert and alert.acknowledged_at is None:
            alert.acknowledged_at = datetime.now(timezone.utc)
            alert.acknowledged_by = user_id
            await self.db.flush()

    async def create(
        self,
        facility_id: UUID,
        tenant_id: UUID,
        severity: str,
        type_: str,
        message: str,
        value: float | None = None,
        threshold: float | None = None,
    ) -> Alert:
        alert = Alert(
            facility_id=facility_id,
            tenant_id=tenant_id,
            severity=severity,
            type=type_,
            message=message,
            value=value,
            threshold=threshold,
        )
        self.db.add(alert)
        await self.db.flush()
        return alert
