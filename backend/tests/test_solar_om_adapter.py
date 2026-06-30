"""Solar O&M adapter — helper logic + vendored-core import-path sanity.

Importing the adapter pulls in the whole vendored detection core, so this test also
guards that the `backend.services.solar_om.*` import paths resolve under the full deps.
"""
from datetime import datetime, timedelta, timezone

from backend.services.solar_om.models import AlertStatus, Severity
from backend.services.solar_om_adapter import _interval_hours, _serialize


def test_interval_hours_median():
    t0 = datetime(2026, 6, 29, 3, tzinfo=timezone.utc)
    ts = [t0, t0 + timedelta(hours=1), t0 + timedelta(hours=2)]
    assert _interval_hours(ts) == 1.0
    assert _interval_hours([t0]) == 0.25     # single sample → safe default


def test_serialize_enums_and_datetimes():
    t0 = datetime(2026, 6, 29, 3, tzinfo=timezone.utc)
    out = _serialize({"severity": Severity.CRITICAL, "status": AlertStatus.OPEN,
                      "opened_at": t0, "rupee_impact_per_day": 3420.0})
    assert out["severity"] == "critical"
    assert out["status"] == "open"
    assert out["opened_at"].startswith("2026-06-29T03:00")
    assert out["rupee_impact_per_day"] == 3420.0
