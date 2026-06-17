"""Alert evaluation + Twilio WhatsApp delivery."""
import logging
from datetime import datetime, timezone
from uuid import UUID

logger = logging.getLogger(__name__)


# pf_threshold / pf_penalty_pct model the industrial power-factor penalty:
# pf_penalty_pct % of (energy + demand) charges for each 0.01 of PF below
# pf_threshold. Approximate per-DISCOM defaults — confirm vs the actual tariff order.
INDIA_TARIFFS = {
    "West Bengal - CESC"    : {"cheap": 4.20, "normal": 6.10, "peak": 7.85, "demand_per_kw": 320, "cheap_hours": list(range(10,16)), "peak_hours": list(range(18,23)), "pf_threshold": 0.95, "pf_penalty_pct": 1.0},
    "Maharashtra - MSEDCL"  : {"cheap": 3.80, "normal": 5.90, "peak": 8.20, "demand_per_kw": 280, "cheap_hours": list(range(10,16)), "peak_hours": list(range(18,22)), "pf_threshold": 0.95, "pf_penalty_pct": 1.0},
    "Tamil Nadu - TANGEDCO" : {"cheap": 4.50, "normal": 6.40, "peak": 8.10, "demand_per_kw": 350, "cheap_hours": list(range(10,17)), "peak_hours": list(range(18,23)), "pf_threshold": 0.95, "pf_penalty_pct": 1.0},
    "Karnataka - BESCOM"    : {"cheap": 4.10, "normal": 6.00, "peak": 7.70, "demand_per_kw": 295, "cheap_hours": list(range(10,16)), "peak_hours": list(range(18,22)), "pf_threshold": 0.90, "pf_penalty_pct": 1.0},
    "Delhi - BSES/TPDDL"    : {"cheap": 3.90, "normal": 5.80, "peak": 7.50, "demand_per_kw": 260, "cheap_hours": list(range(10,16)), "peak_hours": list(range(17,22)), "pf_threshold": 0.95, "pf_penalty_pct": 1.0},
}


def send_whatsapp_alert(to_number: str, message: str) -> bool:
    """Send WhatsApp alert via Twilio. Returns True if delivered."""
    from backend.core.config import get_settings
    settings = get_settings()

    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        logger.warning("Twilio not configured — skipping WhatsApp alert")
        return False

    try:
        from twilio.rest import Client
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.messages.create(
            from_=settings.twilio_whatsapp_from,
            to=f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number,
            body=message,
        )
        logger.info("WhatsApp sent to %s", to_number)
        return True
    except Exception as exc:
        logger.error("WhatsApp send failed: %s", exc)
        return False


def format_alert_message(facility_name: str, severity: str, alert_type: str, message: str) -> str:
    icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵", "OK": "🟢"}.get(severity, "⚪")
    return (
        f"{icon} *MicroGrid AI Alert*\n"
        f"*Facility:* {facility_name}\n"
        f"*Severity:* {severity}\n"
        f"*Type:* {alert_type}\n"
        f"*Details:* {message}\n"
        f"_Sent at {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}_"
    )


def get_current_tariff_rate(state_tariff: str, hour: int) -> tuple[float, str]:
    """Returns (rate_inr, period_name) for a given state and hour."""
    tariff = INDIA_TARIFFS.get(state_tariff, INDIA_TARIFFS["West Bengal - CESC"])
    if hour in tariff["cheap_hours"]:
        return tariff["cheap"], "cheap"
    if hour in tariff["peak_hours"]:
        return tariff["peak"], "peak"
    return tariff["normal"], "normal"
