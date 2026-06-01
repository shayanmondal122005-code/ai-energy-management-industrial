"""Readings repository — all DB access for sensor readings."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Reading
from backend.models.schemas import IngestResponse, ReadingIngest, StatsResponse


class ReadingsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def insert(self, facility_id: UUID, payload: ReadingIngest) -> int:
        reading = Reading(
            facility_id=facility_id,
            timestamp=payload.timestamp,
            load_kw=payload.load_kw,
            solar_kw=payload.solar_kw,
            battery_soc=payload.battery_soc,
            battery_temp=payload.battery_temp,
            grid_kw=payload.grid_kw,
            net_kw=payload.net_kw,
            source=payload.source,
        )
        self.db.add(reading)
        await self.db.flush()

        # Return total count for this facility
        result = await self.db.execute(
            select(func.count()).where(Reading.facility_id == facility_id)
        )
        return result.scalar_one()

    async def get_latest(self, facility_id: UUID) -> Reading | None:
        result = await self.db.execute(
            select(Reading)
            .where(Reading.facility_id == facility_id)
            .order_by(Reading.timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_recent_raw(self, facility_id: UUID, hours: int = 48) -> list[Reading]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.db.execute(
            select(Reading)
            .where(Reading.facility_id == facility_id, Reading.timestamp >= since)
            .order_by(Reading.timestamp.asc())
        )
        return list(result.scalars().all())

    async def get_history_hourly(self, facility_id: UUID, hours: int = 600):
        """Return pre-aggregated hourly rows from readings_hourly table."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.db.execute(
            text("""
                SELECT hour, load_kw_avg, solar_kw_avg, battery_soc_avg
                FROM readings_hourly
                WHERE facility_id = :fid AND hour >= :since
                ORDER BY hour ASC
                LIMIT :lim
            """),
            {"fid": str(facility_id), "since": since, "lim": hours},
        )
        return result.fetchall()

    async def get_stats(self, facility_id: UUID) -> StatsResponse:
        result = await self.db.execute(
            select(
                func.avg(Reading.load_kw).label("avg_load"),
                func.max(Reading.load_kw).label("peak_load"),
                func.avg(Reading.solar_kw).label("avg_solar"),
                func.count().label("total"),
                func.min(Reading.timestamp).label("from_ts"),
                func.max(Reading.timestamp).label("to_ts"),
            ).where(Reading.facility_id == facility_id)
        )
        row = result.one()
        return StatsResponse(
            facility_id=facility_id,
            avg_load_kw=float(row.avg_load or 0),
            peak_load_kw=float(row.peak_load or 0),
            avg_solar_kw=float(row.avg_solar or 0),
            total_readings=int(row.total or 0),
            data_from=row.from_ts,
            data_to=row.to_ts,
        )
