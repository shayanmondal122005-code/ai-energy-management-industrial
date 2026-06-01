"""Background tasks — decision cycle, alerts, reports, retention."""
import logging

logger = logging.getLogger(__name__)


async def run_decision_cycle_all() -> None:
    """Run brain decision cycle for every active facility."""
    logger.info("Running decision cycle for all active facilities")
    # TODO: query active facilities, run brain.run() for each, store alerts


async def run_solar_health_all() -> None:
    """Run 4-detector solar health check for every active facility."""
    logger.info("Running solar health check for all active facilities")
    # TODO: query active facilities, run solar_health.run_solar_health() for each


async def run_alert_checks() -> None:
    """Evaluate alert conditions and send WhatsApp for undelivered critical alerts."""
    logger.info("Running alert checks")
    # TODO: check undelivered critical alerts, send via Twilio, mark whatsapp_sent


async def run_weekly_reports() -> None:
    """Generate weekly PDF reports for all active facilities."""
    logger.info("Generating weekly reports for all facilities")
    # TODO: for each facility, call report_service.generate_weekly(), upload to Supabase Storage


async def run_data_retention() -> None:
    """Delete raw readings older than 90 days (hourly aggregates kept forever)."""
    logger.info("Running data retention policy")
    # TODO: call run_retention_policy() stored procedure via DB
