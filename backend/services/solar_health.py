"""Solar health monitoring — 4 detectors.
Preserves all existing physics logic from the prototype exactly.
"""
import math
from datetime import datetime, timezone
from typing import Any


def run_solar_health(readings: list[Any], solar_cap: float = 200.0) -> dict:
    """
    Runs all 4 solar health detectors on recent readings.
    readings: list of Reading ORM objects or dicts with solar_kw, timestamp fields.
    Returns dict with alerts list and performance_ratio.
    """
    if len(readings) < 4:
        return {"status": "insufficient_data", "alerts": [], "performance_ratio": 1.0}

    alerts = []
    pr     = 1.0

    def _solar(r) -> float:
        return float(getattr(r, "solar_kw", None) or r.get("solar_kw", 0))

    def _ts(r) -> datetime:
        ts = getattr(r, "timestamp", None) or r.get("timestamp")
        if isinstance(ts, str):
            return datetime.fromisoformat(ts)
        return ts

    # ── DETECTOR 1: Panel soiling (Performance Ratio) ──────
    daytime = [r for r in readings if 9 <= _ts(r).hour <= 15]
    if len(daytime) >= 4:
        avg_solar  = sum(_solar(r) for r in daytime) / len(daytime)
        theoretical = solar_cap * 0.65
        pr = avg_solar / theoretical if theoretical > 0 else 1.0

        if pr < 0.75:
            alerts.append({
                "type": "SOILING", "severity": "WARNING",
                "message": (
                    f"Panel Performance Ratio {pr:.2f} below 0.75 threshold. "
                    f"Panels likely dirty. Cleaning recovers ~{(0.95-pr)*theoretical:.0f} kW."
                ),
                "action": "Schedule panel cleaning within 72 hours",
            })
        elif pr < 0.85:
            alerts.append({
                "type": "SOILING", "severity": "INFO",
                "message": f"Performance Ratio {pr:.2f} — slight degradation. Monitor.",
                "action": "Watch over next 3 days",
            })

    # ── DETECTOR 2: Sudden output drop (fault / fire risk) ─
    last4 = readings[-4:]
    drop  = _solar(last4[0]) - _solar(last4[-1])
    h_now = _ts(readings[-1]).hour
    if drop > 50 and 9 <= h_now <= 16:
        alerts.append({
            "type": "SUDDEN_DROP", "severity": "CRITICAL",
            "message": (
                f"Solar output dropped {drop:.0f} kW in 1 hour with no weather event. "
                "Possible loose connection or inverter fault — fire risk."
            ),
            "action": "Inspect inverter and connections IMMEDIATELY",
        })

    # ── DETECTOR 3: Week-over-week degradation ──────────────
    if len(readings) >= 7 * 24 * 2:
        this_week = readings[-(7 * 24 * 4):]
        last_week = readings[-(14 * 24 * 4):-(7 * 24 * 4)]
        tw_avg = sum(_solar(r) for r in this_week) / max(1, len(this_week))
        lw_avg = sum(_solar(r) for r in last_week) / max(1, len(last_week))
        if lw_avg > 5:
            drop_pct = (lw_avg - tw_avg) / lw_avg * 100
            if drop_pct > 15:
                alerts.append({
                    "type": "DEGRADATION", "severity": "WARNING",
                    "message": (
                        f"Solar output down {drop_pct:.0f}% vs last week "
                        f"({tw_avg:.0f} vs {lw_avg:.0f} kW avg). "
                        "Panel failure or soiling — thermographic scan recommended."
                    ),
                    "action": "Arrange thermographic inspection",
                })

    # ── DETECTOR 4: Storm warning (Open-Meteo) ──────────────
    try:
        import requests
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 22.57, "longitude": 88.36,
                "hourly": "windspeed_10m,precipitation_probability",
                "forecast_days": 2, "timezone": "Asia/Kolkata",
            },
            timeout=5,
        )
        if r.status_code == 200:
            wdata    = r.json()["hourly"]
            max_wind = max(wdata["windspeed_10m"][:48])
            max_rain = max(wdata["precipitation_probability"][:48])
            if max_wind > 15 and max_rain > 70:
                alerts.append({
                    "type": "STORM", "severity": "WARNING",
                    "message": (
                        f"Storm forecast. Max wind: {max_wind:.0f} km/h, "
                        f"rain probability: {max_rain:.0f}%."
                    ),
                    "action": "Physical structural mounting check",
                })
    except Exception:
        pass

    return {
        "status": "ok",
        "alerts_count": len(alerts),
        "alerts": alerts,
        "performance_ratio": round(pr, 3),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
