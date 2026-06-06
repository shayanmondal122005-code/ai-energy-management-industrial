"""Readings repository — all DB access for sensor readings."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Reading
from backend.models.schemas import IngestResponse, ReadingIngest, SolarGenerationResponse, StatsResponse

IST = timezone(timedelta(hours=5, minutes=30))
GRID_CO2_KG_PER_KWH = 0.71  # India grid emission factor (CEA)


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

    async def get_solar_generation(self, facility_id: UUID) -> SolarGenerationResponse:
        """Solar energy (kWh) = average power × time span, per window.
        Robust to irregular sampling (hourly seed + 2-min live)."""
        now_ist     = datetime.now(IST)
        now_utc     = datetime.now(timezone.utc)
        day_start   = now_ist.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        month_start = now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

        async def energy_since(since_utc) -> float:
            res = await self.db.execute(
                select(
                    func.avg(Reading.solar_kw),
                    func.min(Reading.timestamp),
                    func.max(Reading.timestamp),
                    func.count(),
                ).where(Reading.facility_id == facility_id, Reading.timestamp >= since_utc)
            )
            avg, mn, mx, cnt = res.one()
            if not cnt or avg is None or mn is None or mx is None:
                return 0.0
            span_h = (mx - mn).total_seconds() / 3600
            return float(avg) * span_h

        today_kwh = await energy_since(day_start)
        month_kwh = await energy_since(month_start)

        # lifetime
        res = await self.db.execute(
            select(
                func.avg(Reading.solar_kw),
                func.min(Reading.timestamp),
                func.max(Reading.timestamp),
                func.count(),
            ).where(Reading.facility_id == facility_id)
        )
        avg_all, mn_all, mx_all, cnt_all = res.one()
        total_kwh = 0.0
        if cnt_all and avg_all is not None and mn_all and mx_all:
            total_kwh = float(avg_all) * ((mx_all - mn_all).total_seconds() / 3600)

        # peak instantaneous today
        res2 = await self.db.execute(
            select(func.max(Reading.solar_kw))
            .where(Reading.facility_id == facility_id, Reading.timestamp >= day_start)
        )
        peak_today = float(res2.scalar() or 0)

        return SolarGenerationResponse(
            facility_id=facility_id,
            today_kwh=round(today_kwh, 1),
            month_kwh=round(month_kwh, 1),
            total_kwh=round(total_kwh, 1),
            peak_today_kw=round(peak_today, 1),
            co2_avoided_today_kg=round(today_kwh * GRID_CO2_KG_PER_KWH, 1),
            updated_at=now_utc,
        )

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
