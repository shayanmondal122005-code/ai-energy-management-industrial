"""Readings repository — all DB access for sensor readings."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Reading
from backend.models.schemas import IngestResponse, ReadingIngest, SolarGenerationResponse, StatsResponse
from backend.services.solar_roi import energy_kwh

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

    async def get_hourly_for_shadow(self, facility_id: UUID, days: int = 30):
        """Hourly avg load/solar/soc over the last N days — feeds shadow-savings replay.
        One row per hour with data. Aggregates directly from raw readings (portable,
        no dependency on the readings_hourly rollup being populated)."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            text("""
                SELECT date_trunc('hour', timestamp) AS hr,
                       AVG(load_kw)     AS load_kw,
                       AVG(solar_kw)    AS solar_kw,
                       AVG(battery_soc) AS soc
                FROM readings
                WHERE facility_id = :fid AND timestamp >= :since
                GROUP BY 1
                ORDER BY 1 ASC
            """),
            {"fid": str(facility_id), "since": since},
        )
        return result.fetchall()

    async def get_solar_generation(self, facility_id: UUID) -> SolarGenerationResponse:
        """Solar energy (kWh) = average power × time span, per window.
        Single round-trip using conditional aggregates (FILTER) — fast over WAN."""
        now_ist     = datetime.now(IST)
        now_utc     = datetime.now(timezone.utc)
        day_start   = now_ist.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        month_start = now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

        row = (await self.db.execute(
            text("""
                SELECT
                  AVG(solar_kw) FILTER (WHERE timestamp >= :day)   AS day_avg,
                  MIN(timestamp) FILTER (WHERE timestamp >= :day)  AS day_min,
                  MAX(timestamp) FILTER (WHERE timestamp >= :day)  AS day_max,
                  MAX(solar_kw) FILTER (WHERE timestamp >= :day)   AS day_peak,
                  AVG(solar_kw) FILTER (WHERE timestamp >= :month) AS mon_avg,
                  MIN(timestamp) FILTER (WHERE timestamp >= :month) AS mon_min,
                  MAX(timestamp) FILTER (WHERE timestamp >= :month) AS mon_max,
                  AVG(solar_kw) AS all_avg,
                  MIN(timestamp) AS all_min,
                  MAX(timestamp) AS all_max
                FROM readings
                WHERE facility_id = :fid
            """),
            {"fid": str(facility_id), "day": day_start, "month": month_start},
        )).one()

        # energy_kwh (avg power × elapsed hours) is unit-tested in services/solar_roi.py
        today_kwh = energy_kwh(row.day_avg, row.day_min, row.day_max)
        month_kwh = energy_kwh(row.mon_avg, row.mon_min, row.mon_max)
        total_kwh = energy_kwh(row.all_avg, row.all_min, row.all_max)
        peak_today = float(row.day_peak or 0)

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
