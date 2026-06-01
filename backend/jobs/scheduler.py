"""APScheduler setup — all background jobs for MicroGrid AI."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.core.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def start_scheduler() -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    from backend.jobs.tasks import (
        run_decision_cycle_all,
        run_solar_health_all,
        run_alert_checks,
        run_data_retention,
        run_weekly_reports,
        run_optimizer_all,
        run_dispatch_commands,
        run_watchdog_all,
    )

    # ── WATCHDOG — highest priority, runs every 2 minutes ──
    # Detects malfunctions → safe mode → WhatsApp before any power cut
    _scheduler.add_job(
        run_watchdog_all,
        IntervalTrigger(minutes=2),
        id="watchdog", replace_existing=True,
    )

    # LP optimizer runs every morning at 6am IST — builds full 24h schedule
    _scheduler.add_job(
        run_optimizer_all,
        CronTrigger(hour=6, minute=0, timezone="Asia/Kolkata"),
        id="optimizer_daily", replace_existing=True,
    )

    # Also re-optimize every hour (fresh forecast data)
    _scheduler.add_job(
        run_optimizer_all,
        IntervalTrigger(hours=1),
        id="optimizer_hourly", replace_existing=True,
    )

    # Execute battery commands every 15 min based on today's schedule
    _scheduler.add_job(
        run_dispatch_commands,
        IntervalTrigger(minutes=settings.decision_cycle_interval_minutes),
        id="dispatch_commands", replace_existing=True,
    )

    # Decision cycle + solar health every 15 minutes
    _scheduler.add_job(
        run_decision_cycle_all,
        IntervalTrigger(minutes=settings.decision_cycle_interval_minutes),
        id="decision_cycle", replace_existing=True,
    )
    _scheduler.add_job(
        run_solar_health_all,
        IntervalTrigger(minutes=settings.decision_cycle_interval_minutes),
        id="solar_health", replace_existing=True,
    )

    # Alert evaluation every 5 minutes
    _scheduler.add_job(
        run_alert_checks,
        IntervalTrigger(minutes=settings.alert_check_interval_minutes),
        id="alert_checks", replace_existing=True,
    )

    # Weekly PDF reports — Monday 8am IST
    _scheduler.add_job(
        run_weekly_reports,
        CronTrigger(day_of_week="mon", hour=8, minute=0, timezone="Asia/Kolkata"),
        id="weekly_reports", replace_existing=True,
    )

    # Data retention — midnight IST daily
    _scheduler.add_job(
        run_data_retention,
        CronTrigger(hour=0, minute=0, timezone="Asia/Kolkata"),
        id="data_retention", replace_existing=True,
    )

    _scheduler.start()
    logger.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
