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
