"""Background tasks — decision cycle, alerts, reports, retention.
Each task opens its own DB session — safe for concurrent runs.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def _get_active_facilities():
    """Return all active facilities from DB."""
    from backend.core.database import AsyncSessionLocal
    from backend.repositories.facilities_repo import FacilitiesRepository
    from sqlalchemy import select
    from backend.models.database import Facility

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Facility).where(Facility.is_active == True)
        )
        return list(result.scalars().all())


async def run_decision_cycle_all() -> None:
    """Run brain decision cycle for every active facility. Writes alerts to DB."""
    from backend.core.database import AsyncSessionLocal
    from backend.repositories.readings_repo import ReadingsRepository
    from backend.repositories.alerts_repo import AlertsRepository
    from backend.services.forecasting import readings_to_dataframe, add_time_features, train_load_model, predict_next_24h
    from backend.services.battery_tracker import BatteryTracker
    from backend.services.brain import MicrogridBrain
    from backend.services.alert_service import send_whatsapp_alert, format_alert_message, get_current_tariff_rate

    facilities = await _get_active_facilities()
    logger.info("Decision cycle for %d facilities", len(facilities))

    for facility in facilities:
        try:
            async with AsyncSessionLocal() as db:
                r_repo = ReadingsRepository(db)
                a_repo = AlertsRepository(db)

                readings = await r_repo.get_recent_raw(facility.id, hours=240)
                if len(readings) < 48:
                    logger.warning("facility=%s has only %d readings — skipping", facility.id, len(readings))
                    continue

                df_raw = readings_to_dataframe(readings)
                df     = add_time_features(df_raw)

                model, _, _ = train_load_model(df)
                forecast    = predict_next_24h(model, df.tail(200))

                latest = readings[-1]
                battery = BatteryTracker({
                    "capacity_kwh" : facility.battery_kwh,
                    "initial_soc"  : float(getattr(latest, "battery_soc", 70)) / 100,
                })
                brain = MicrogridBrain(battery)
                decision = brain.run(
                    current_hour    =datetime.now(timezone.utc).hour,
                    current_load_kw =float(latest.load_kw),
                    current_solar_kw=float(latest.solar_kw),
                    forecast_load   =forecast["forecast_kw"].tolist(),
                    forecast_solar  =[max(0, facility.solar_kw * __import__("math").sin(
                        (h % 24 - 6) * __import__("math").pi / 12
                    )) if 6 <= (h % 24) <= 18 else 0 for h in range(24)],
                    temp_c          =float(getattr(latest, "battery_temp", 28) or 28),
                )

                for alert in decision["alerts"]:
                    if alert["severity"] in ("CRITICAL", "WARNING"):
                        await a_repo.create(
                            facility_id=facility.id,
                            tenant_id=facility.tenant_id,
                            severity=alert["severity"].lower(),
                            type_=alert["type"],
                            message=alert["message"],
                            value=alert.get("value"),
                            threshold=alert.get("threshold"),
                        )
                await db.commit()

        except Exception as exc:
            logger.error("Decision cycle failed for facility=%s: %s", facility.id, exc)


async def run_solar_health_all() -> None:
    """Run solar health checks for all active facilities."""
    from backend.core.database import AsyncSessionLocal
    from backend.repositories.readings_repo import ReadingsRepository
    from backend.repositories.alerts_repo import AlertsRepository
    from backend.services.solar_health import run_solar_health

    facilities = await _get_active_facilities()
    for facility in facilities:
        try:
            async with AsyncSessionLocal() as db:
                r_repo   = ReadingsRepository(db)
                a_repo   = AlertsRepository(db)
                readings = await r_repo.get_recent_raw(facility.id, hours=48)
                result   = run_solar_health(readings, solar_cap=facility.solar_kw)

                for alert in result.get("alerts", []):
                    if alert["severity"] in ("CRITICAL", "WARNING"):
                        await a_repo.create(
                            facility_id=facility.id,
                            tenant_id=facility.tenant_id,
                            severity=alert["severity"].lower(),
                            type_=alert["type"],
                            message=alert["message"],
                        )
                await db.commit()
        except Exception as exc:
            logger.error("Solar health failed for facility=%s: %s", facility.id, exc)


async def run_alert_checks() -> None:
    """Send WhatsApp for CRITICAL alerts not yet delivered."""
    from backend.core.database import AsyncSessionLocal
    from sqlalchemy import select
    from backend.models.database import Alert, User, Facility

    async with AsyncSessionLocal() as db:
        # Find undelivered critical alerts from last 30 min
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        result = await db.execute(
            select(Alert)
            .where(
                Alert.severity == "critical",
                Alert.whatsapp_sent == False,
                Alert.created_at >= cutoff,
            )
            .limit(50)
        )
        alerts = list(result.scalars().all())

        from backend.services.alert_service import send_whatsapp_alert, format_alert_message
        for alert in alerts:
            fac = await db.get(Facility, alert.facility_id)
            if not fac:
                continue
            users = await db.execute(
                select(User).where(
                    User.tenant_id == alert.tenant_id,
                    User.whatsapp.isnot(None),
                    User.is_active == True,
                    User.role.in_(["operator", "tenant_admin", "super_admin"]),
                )
            )
            for user in users.scalars().all():
                msg = format_alert_message(fac.name, alert.severity.upper(), alert.type, alert.message)
                sent = send_whatsapp_alert(user.whatsapp, msg)
                if sent:
                    alert.whatsapp_sent    = True
                    alert.whatsapp_sent_at = datetime.now(timezone.utc)

        await db.commit()
    logger.info("Alert check: processed %d undelivered critical alerts", len(alerts))


async def run_optimizer_all() -> None:
    """Run LP optimizer for every active facility. Stores schedule in Redis."""
    from backend.core.database import AsyncSessionLocal
    from backend.repositories.readings_repo import ReadingsRepository
    from backend.repositories.facilities_repo import FacilitiesRepository
    from backend.services.forecasting import readings_to_dataframe, add_time_features, train_load_model, predict_next_24h
    from backend.services.optimizer import optimize_dispatch
    from backend.services.alert_service import INDIA_TARIFFS
    from backend.core.cache import cache_set
    import math

    facilities = await _get_active_facilities()
    logger.info("Running LP optimizer for %d facilities", len(facilities))

    for facility in facilities:
        try:
            async with AsyncSessionLocal() as db:
                r_repo   = ReadingsRepository(db)
                readings = await r_repo.get_recent_raw(facility.id, hours=240)
                if len(readings) < 48:
                    continue

                df_raw = readings_to_dataframe(readings)
                df     = add_time_features(df_raw)
                model, _, _ = train_load_model(df)
                fc     = predict_next_24h(model, df.tail(200))
                load_fc = fc["forecast_kw"].tolist()

                hour_now = datetime.now(timezone.utc).hour
                solar_fc = [
                    max(0.0, facility.solar_kw * math.sin((h % 24 - 6) * math.pi / 12) * 0.82)
                    if 6 <= (h % 24) <= 18 else 0.0
                    for h in range(hour_now, hour_now + 24)
                ]

                tariff = INDIA_TARIFFS.get(facility.state_tariff, INDIA_TARIFFS["West Bengal - CESC"])
                price_fc = []
                for offset in range(24):
                    h = (hour_now + offset) % 24
                    if h in tariff["cheap_hours"]:
                        price_fc.append(tariff["cheap"])
                    elif h in tariff["peak_hours"]:
                        price_fc.append(tariff["peak"])
                    else:
                        price_fc.append(tariff["normal"])

                latest      = readings[-1]
                current_soc = float(getattr(latest, "battery_soc", 70)) / 100

                schedule = optimize_dispatch(
                    load_forecast=load_fc,
                    solar_forecast=solar_fc,
                    tariff_schedule=price_fc,
                    current_soc=current_soc,
                    battery_kwh=facility.battery_kwh,
                )

                # Store schedule in Redis — dispatch job reads this every 15 min
                await cache_set(
                    f"dispatch_schedule:{facility.id}",
                    {
                        "charge_kw"   : schedule.charge_kw,
                        "discharge_kw": schedule.discharge_kw,
                        "grid_kw"     : schedule.grid_kw,
                        "hour_base"   : hour_now,
                        "status"      : schedule.status,
                        "savings"     : schedule.savings,
                    },
                    ttl_seconds=86400,
                )
                logger.info(
                    "Optimizer: facility=%s status=%s savings=₹%.0f",
                    facility.name, schedule.status, schedule.savings,
                )
        except Exception as exc:
            logger.error("Optimizer failed for facility=%s: %s", facility.id, exc)


async def run_dispatch_commands() -> None:
    """
    Every 15 minutes: read today's optimal schedule from Redis
    and write the current-hour battery command to grid_state table.
    This is what physically controls the battery (via Modbus when connected).
    """
    from backend.core.database import AsyncSessionLocal
    from backend.core.cache import cache_get
    from backend.services.optimizer import get_current_hour_command, OptimalSchedule
    from sqlalchemy import select
    from backend.models.database import GridState

    facilities = await _get_active_facilities()

    for facility in facilities:
        try:
            schedule_data = await cache_get(f"dispatch_schedule:{facility.id}")
            if not schedule_data:
                logger.debug("No schedule in cache for facility=%s — skipping dispatch", facility.id)
                continue

            hour_now     = datetime.now(timezone.utc).hour
            hour_base    = schedule_data["hour_base"]
            hour_offset  = (hour_now - hour_base) % 24

            charge_kw    = schedule_data["charge_kw"]
            discharge_kw = schedule_data["discharge_kw"]

            c = charge_kw[hour_offset]    if hour_offset < 24 else 0.0
            d = discharge_kw[hour_offset] if hour_offset < 24 else 0.0

            command = "CHARGE" if c > 1.0 else "DISCHARGE" if d > 1.0 else "HOLD"

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(GridState).where(GridState.facility_id == facility.id)
                )
                gs = result.scalar_one_or_none()
                if gs and gs.battery_command != command:
                    gs.battery_command = command
                    await db.commit()
                    logger.info(
                        "Dispatch: facility=%s hour=%d → %s (charge=%.0fkW discharge=%.0fkW)",
                        facility.name, hour_now, command, c, d,
                    )
        except Exception as exc:
            logger.error("Dispatch failed for facility=%s: %s", facility.id, exc)


async def run_watchdog_all() -> None:
    """
    Runs every 2 minutes for every active facility.
    Detects malfunctions → activates safe mode → sends WhatsApp instantly.
    This is the highest-priority job — power cut prevention.
    """
    from backend.core.database import AsyncSessionLocal
    from backend.repositories.readings_repo import ReadingsRepository
    from backend.services.watchdog import run_watchdog, format_malfunction_whatsapp
    from backend.services.safe_mode import activate_safe_mode, is_safe_mode_active
    from backend.services.alert_service import send_whatsapp_alert
    from backend.repositories.alerts_repo import AlertsRepository
    from sqlalchemy import select
    from backend.models.database import User

    facilities = await _get_active_facilities()

    for facility in facilities:
        try:
            async with AsyncSessionLocal() as db:
                r_repo   = ReadingsRepository(db)
                readings = await r_repo.get_recent_raw(facility.id, hours=1)

                # Check cached optimizer status
                from backend.core.cache import cache_get
                opt_cache = await cache_get(f"dispatch_schedule:{facility.id}")
                opt_status = opt_cache.get("status") if opt_cache else None

                result = run_watchdog(
                    readings=readings,
                    facility_name=facility.name,
                    facility_id=str(facility.id),
                    solar_kw_installed=facility.solar_kw,
                    optimizer_status=opt_status,
                )

                if not result.safe:
                    malfunction_types = [m.type.value for m in result.malfunctions]
                    critical_faults   = [m for m in result.malfunctions if m.severity == "critical"]

                    # ── Activate safe mode (force grid + HOLD + shed P4-P5) ──
                    safe_actions = await activate_safe_mode(
                        facility_id=facility.id,
                        tenant_id=facility.tenant_id,
                        malfunction_types=malfunction_types,
                        db=db,
                    )

                    # ── Write critical alerts to DB ──────────────────────────
                    a_repo = AlertsRepository(db)
                    for m in result.malfunctions:
                        await a_repo.create(
                            facility_id=facility.id,
                            tenant_id=facility.tenant_id,
                            severity=m.severity,
                            type_=m.type.value,
                            message=m.message,
                            value=m.value,
                            threshold=m.threshold,
                        )
                    await db.commit()

                    # ── Send WhatsApp to ALL operators + Shayan (super_admin) ──
                    if critical_faults:
                        users_result = await db.execute(
                            select(User).where(
                                User.whatsapp.isnot(None),
                                User.is_active == True,
                                User.role.in_(["operator", "tenant_admin", "super_admin"]),
                            )
                        )
                        users = list(users_result.scalars().all())

                        for user in users:
                            is_shayan = user.role == "super_admin"
                            msg = format_malfunction_whatsapp(result, is_shayan=is_shayan)
                            sent = send_whatsapp_alert(user.whatsapp, msg)
                            logger.info(
                                "Watchdog WhatsApp → %s (%s): sent=%s",
                                user.email, user.role, sent,
                            )

                    logger.critical(
                        "WATCHDOG: facility=%s faults=%d safe_mode=%s shed_kw=%.0f",
                        facility.name, len(result.malfunctions),
                        result.safe, safe_actions.get("shed_kw", 0),
                    )

        except Exception as exc:
            logger.error("Watchdog failed for facility=%s: %s", facility.id, exc)


async def run_weekly_reports() -> None:
    """Generate weekly PDF reports for all active facilities."""
    logger.info("Weekly report generation — TODO: implement reportlab PDF generation")
    # TODO Phase 3: generate PDF with reportlab, upload to Supabase Storage, send WhatsApp link


async def run_data_retention() -> None:
    """Delete raw readings older than 90 days."""
    from backend.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT run_retention_policy()"))
        await db.commit()
    logger.info("Retention policy executed")
