"""Grid repository — grid state, commands, loads, audit log."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import AuditLog, ControlCommand, GridState, LoadConfig
from backend.core.config import get_settings

settings = get_settings()


class GridRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_state(self, facility_id: UUID) -> GridState | None:
        result = await self.db.execute(
            select(GridState).where(GridState.facility_id == facility_id)
        )
        return result.scalar_one_or_none()

    async def get_loads(self, facility_id: UUID) -> list[LoadConfig]:
        result = await self.db.execute(
            select(LoadConfig)
            .where(LoadConfig.facility_id == facility_id)
            .order_by(LoadConfig.priority, LoadConfig.shed_order)
        )
        return list(result.scalars().all())

    async def get_load(self, facility_id: UUID, load_id: str) -> LoadConfig | None:
        result = await self.db.execute(
            select(LoadConfig).where(
                LoadConfig.facility_id == facility_id,
                LoadConfig.load_id == load_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_command(
        self,
        facility_id: UUID,
        tenant_id: UUID,
        type: str,
        reason: str,
        issued_by: UUID,
        issued_by_ip: str | None = None,
        target: str | None = None,
        value: float | None = None,
        priority: str = "normal",
    ) -> ControlCommand:
        cmd = ControlCommand(
            facility_id=facility_id,
            tenant_id=tenant_id,
            type=type,
            target=target,
            value=value,
            reason=reason,
            priority=priority,
            issued_by=issued_by,
            issued_by_ip=issued_by_ip,
            expires_at=datetime.now(timezone.utc) + timedelta(
                seconds=settings.command_confirmation_timeout_seconds
            ),
        )
        self.db.add(cmd)
        await self.db.flush()
        await self.db.refresh(cmd)
        return cmd

    async def confirm_and_execute(self, command_id: UUID, confirmed_by: UUID) -> ControlCommand:
        result = await self.db.execute(
            select(ControlCommand).where(ControlCommand.id == command_id)
        )
        cmd = result.scalar_one_or_none()
        if cmd is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Command not found")

        now = datetime.now(timezone.utc)
        if cmd.expires_at < now:
            raise HTTPException(status_code=410, detail="Command expired — reissue the command")
        if cmd.confirmed:
            raise HTTPException(status_code=409, detail="Command already confirmed")

        cmd.confirmed    = True
        cmd.confirmed_at = now
        cmd.confirmed_by = confirmed_by
        cmd.executed     = True
        cmd.executed_at  = now
        cmd.result       = "success"

        # Apply grid state change
        await self._apply_command(cmd)

        # Write audit log
        audit = AuditLog(
            facility_id=cmd.facility_id,
            tenant_id=cmd.tenant_id,
            user_id=confirmed_by,
            event=cmd.type,
            data={"command_id": str(command_id), "target": cmd.target, "reason": cmd.reason},
            ip_address=str(cmd.issued_by_ip) if cmd.issued_by_ip else None,
        )
        self.db.add(audit)
        await self.db.flush()
        return cmd

    async def _apply_command(self, cmd: ControlCommand) -> None:
        """Apply the command effect to grid_state / load_configs."""
        if cmd.type == "ISLAND":
            gs = await self.get_state(cmd.facility_id)
            if gs:
                gs.mode             = "ISLAND"
                gs.main_breaker     = False
                gs.last_mode_change = datetime.now(timezone.utc)

        elif cmd.type == "RECONNECT":
            gs = await self.get_state(cmd.facility_id)
            if gs:
                gs.mode             = "GRID_CONNECTED"
                gs.main_breaker     = True
                gs.last_mode_change = datetime.now(timezone.utc)

        elif cmd.type == "LOAD_SHED" and cmd.target:
            load = await self.get_load(cmd.facility_id, cmd.target)
            if load:
                load.is_on = False

        elif cmd.type == "LOAD_RESTORE" and cmd.target:
            load = await self.get_load(cmd.facility_id, cmd.target)
            if load:
                load.is_on = True

        await self.db.flush()

    async def get_audit_log(self, facility_id: UUID, limit: int = 50) -> list[AuditLog]:
        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.facility_id == facility_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
