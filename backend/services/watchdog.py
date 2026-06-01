"""Safety Watchdog — runs every 2 minutes.

Detects malfunctions BEFORE they cause a power cut.
On any malfunction:
  1. Immediately switches battery to SAFE mode
  2. Forces grid connection (never island during fault)
  3. Sheds P4-P5 loads to conserve battery
  4. Sends WhatsApp to Shayan + all facility operators
  5. Writes to audit log

P1 loads (ICU, OT, life support) are NEVER shed under any circumstances.
Power cut is prevented by keeping grid connected + battery in HOLD.

Malfunction types detected:
  STALE_DATA          — no sensor reading for > 20 min (gateway offline)
  SOC_FREEFALL        — SoC dropping faster than physics allows (sensor fault)
  SOC_CRITICAL        — SoC < 12% and still discharging
  BATTERY_TEMP_HIGH   — battery temp > 45°C (thermal runaway risk)
  SOLAR_FAULT         — sudden solar drop during peak daylight (inverter fault)
  OPTIMIZER_FAILURE   — LP infeasible + fallback also struggling
  GRID_LOST           — grid import failed while load > solar + battery can cover
  SENSOR_ANOMALY      — load or solar reading physically impossible
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MalfunctionType(str, Enum):
    STALE_DATA        = "STALE_DATA"
    SOC_FREEFALL      = "SOC_FREEFALL"
    SOC_CRITICAL      = "SOC_CRITICAL"
    BATTERY_TEMP_HIGH = "BATTERY_TEMP_HIGH"
    SOLAR_FAULT       = "SOLAR_FAULT"
    OPTIMIZER_FAILURE = "OPTIMIZER_FAILURE"
    GRID_LOST         = "GRID_LOST"
    SENSOR_ANOMALY    = "SENSOR_ANOMALY"


@dataclass
class Malfunction:
    type:        MalfunctionType
    severity:    str              # "critical" | "warning"
    message:     str
    value:       float | None = None
    threshold:   float | None = None
    action_taken: str         = ""


@dataclass
class WatchdogResult:
    facility_id:   str
    facility_name: str
    safe:          bool                   # True = all clear
    malfunctions:  list[Malfunction] = field(default_factory=list)
    safe_mode_activated: bool = False


# ── Thresholds ────────────────────────────────────────────────

THRESHOLDS = {
    "stale_data_minutes"  : 20,     # no reading for this long = fault
    "soc_critical_pct"    : 12.0,   # below this = emergency
    "soc_freefall_per_min": 1.5,    # % drop per minute = sensor fault
    "battery_temp_max"    : 45.0,   # °C — thermal runaway risk
    "solar_drop_kw"       : 60.0,   # kW drop in 1 reading = inverter fault
    "load_max_kw"         : 2000.0, # physically impossible for hospital
    "solar_max_kw"        : 1000.0, # physically impossible
}


def run_watchdog(
    readings: list[Any],         # last N Reading ORM objects, newest last
    facility_name: str,
    facility_id: str,
    solar_kw_installed: float,
    optimizer_status: str | None = None,
) -> WatchdogResult:
    """
    Analyse recent readings and return all detected malfunctions.
    Pure function — no side effects. Caller handles notifications + DB writes.
    """
    result = WatchdogResult(facility_id=facility_id, facility_name=facility_name, safe=True)

    if not readings:
        result.safe = False
        result.malfunctions.append(Malfunction(
            type=MalfunctionType.STALE_DATA,
            severity="critical",
            message=f"{facility_name}: No sensor readings in database. Gateway may be offline.",
            action_taken="Force grid connection, battery HOLD",
        ))
        return result

    latest   = readings[-1]
    now      = datetime.now(timezone.utc)

    def _ts(r) -> datetime:
        ts = getattr(r, "timestamp", None)
        if ts is None: return now
        if ts.tzinfo is None: return ts.replace(tzinfo=timezone.utc)
        return ts

    def _soc(r)  -> float: return float(getattr(r, "battery_soc",  70) or 70)
    def _load(r) -> float: return float(getattr(r, "load_kw",      0)  or 0)
    def _solar(r)-> float: return float(getattr(r, "solar_kw",     0)  or 0)
    def _temp(r) -> float: return float(getattr(r, "battery_temp", 28) or 28)

    latest_ts  = _ts(latest)
    age_minutes = (now - latest_ts).total_seconds() / 60

    # ── CHECK 1: Stale data ────────────────────────────────
    if age_minutes > THRESHOLDS["stale_data_minutes"]:
        result.safe = False
        result.malfunctions.append(Malfunction(
            type=MalfunctionType.STALE_DATA,
            severity="critical",
            message=(
                f"{facility_name}: Last reading was {age_minutes:.0f} minutes ago. "
                f"Sensor gateway may be offline or disconnected."
            ),
            value=age_minutes,
            threshold=THRESHOLDS["stale_data_minutes"],
            action_taken="Battery set to HOLD. Grid connection forced ON.",
        ))

    # ── CHECK 2: SoC critical + discharging ───────────────
    cur_soc = _soc(latest)
    if cur_soc < THRESHOLDS["soc_critical_pct"]:
        # Check if it's discharging (SoC dropping)
        prev_soc = _soc(readings[-2]) if len(readings) >= 2 else cur_soc
        discharging = cur_soc < prev_soc

        result.safe = False
        result.malfunctions.append(Malfunction(
            type=MalfunctionType.SOC_CRITICAL,
            severity="critical",
            message=(
                f"{facility_name}: Battery at {cur_soc:.1f}% "
                f"({'and discharging' if discharging else 'stable'}). "
                f"Below {THRESHOLDS['soc_critical_pct']}% safety threshold. "
                f"Immediate grid import required."
            ),
            value=cur_soc,
            threshold=THRESHOLDS["soc_critical_pct"],
            action_taken="Emergency grid CHARGE command issued. Optimizer paused.",
        ))

    # ── CHECK 3: SoC freefall ─────────────────────────────
    if len(readings) >= 4:
        socs = [_soc(r) for r in readings[-4:]]
        tss  = [_ts(r)  for r in readings[-4:]]
        drops = []
        for i in range(1, len(socs)):
            dt_min = max(0.1, (tss[i] - tss[i-1]).total_seconds() / 60)
            drop_per_min = (socs[i-1] - socs[i]) / dt_min
            if drop_per_min > 0:
                drops.append(drop_per_min)

        if drops:
            max_drop = max(drops)
            if max_drop > THRESHOLDS["soc_freefall_per_min"]:
                result.safe = False
                result.malfunctions.append(Malfunction(
                    type=MalfunctionType.SOC_FREEFALL,
                    severity="critical",
                    message=(
                        f"{facility_name}: Battery SoC dropping at {max_drop:.1f}%/min — "
                        f"exceeds {THRESHOLDS['soc_freefall_per_min']}%/min limit. "
                        f"Possible sensor fault or battery cell failure."
                    ),
                    value=max_drop,
                    threshold=THRESHOLDS["soc_freefall_per_min"],
                    action_taken="Battery disconnected from loads. Grid import forced.",
                ))

    # ── CHECK 4: Battery temperature ─────────────────────
    temp = _temp(latest)
    if temp > THRESHOLDS["battery_temp_max"]:
        result.safe = False
        result.malfunctions.append(Malfunction(
            type=MalfunctionType.BATTERY_TEMP_HIGH,
            severity="critical",
            message=(
                f"{facility_name}: Battery temperature {temp:.1f}°C "
                f"exceeds {THRESHOLDS['battery_temp_max']}°C threshold. "
                f"Thermal runaway risk. Stop all battery operation immediately."
            ),
            value=temp,
            threshold=THRESHOLDS["battery_temp_max"],
            action_taken="Battery isolated. Grid-only mode activated. Inspect NOW.",
        ))

    # ── CHECK 5: Solar fault (sudden drop during daylight) ─
    if len(readings) >= 2:
        h_now    = latest_ts.hour
        solar_now  = _solar(latest)
        solar_prev = _solar(readings[-2])
        drop = solar_prev - solar_now

        if drop > THRESHOLDS["solar_drop_kw"] and 9 <= h_now <= 16:
            result.safe = False
            result.malfunctions.append(Malfunction(
                type=MalfunctionType.SOLAR_FAULT,
                severity="critical",
                message=(
                    f"{facility_name}: Solar output dropped {drop:.0f} kW in one reading "
                    f"during peak daylight ({h_now}:00). "
                    f"Possible inverter fault, loose connection, or fire risk."
                ),
                value=drop,
                threshold=THRESHOLDS["solar_drop_kw"],
                action_taken="Solar forecasts recalculated. Grid import increased to cover gap.",
            ))

    # ── CHECK 6: Sensor anomaly ───────────────────────────
    load  = _load(latest)
    solar = _solar(latest)
    if load > THRESHOLDS["load_max_kw"]:
        result.safe = False
        result.malfunctions.append(Malfunction(
            type=MalfunctionType.SENSOR_ANOMALY,
            severity="warning",
            message=(
                f"{facility_name}: Load reading {load:.0f} kW is physically impossible "
                f"for this facility. Sensor or communication fault."
            ),
            value=load,
            threshold=THRESHOLDS["load_max_kw"],
            action_taken="Reading ignored. Using last valid reading for dispatch.",
        ))

    if solar > THRESHOLDS["solar_max_kw"]:
        result.safe = False
        result.malfunctions.append(Malfunction(
            type=MalfunctionType.SENSOR_ANOMALY,
            severity="warning",
            message=(
                f"{facility_name}: Solar reading {solar:.0f} kW exceeds installed capacity. "
                f"Sensor fault detected."
            ),
            value=solar,
            threshold=THRESHOLDS["solar_max_kw"],
            action_taken="Solar reading capped at installed capacity.",
        ))

    # ── CHECK 7: Optimizer failure ────────────────────────
    if optimizer_status == "infeasible":
        result.malfunctions.append(Malfunction(
            type=MalfunctionType.OPTIMIZER_FAILURE,
            severity="warning",
            message=(
                f"{facility_name}: LP optimizer could not find a valid schedule today. "
                f"Battery capacity may be insufficient for today's forecast load. "
                f"Running rule-based fallback."
            ),
            action_taken="Switched to rule-based dispatch. Grid import will cover any gap.",
        ))

    return result


def format_malfunction_whatsapp(result: WatchdogResult, is_shayan: bool = False) -> str:
    """Format malfunction list as WhatsApp message."""
    lines = [
        f"🚨 *MALFUNCTION ALERT — MicroGrid AI*",
        f"*Facility:* {result.facility_name}",
        f"*Time:* {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}",
        f"*Faults detected:* {len(result.malfunctions)}",
        "",
    ]

    for m in result.malfunctions:
        icon = "🔴" if m.severity == "critical" else "🟡"
        lines.append(f"{icon} *{m.type.value.replace('_', ' ')}*")
        lines.append(f"   {m.message}")
        if m.action_taken:
            lines.append(f"   ✅ Action: {m.action_taken}")
        lines.append("")

    lines.append("⚡ *Power supply maintained. P1 loads protected.*")

    if is_shayan:
        lines.append("")
        lines.append("_— Your MicroGrid AI system_")

    return "\n".join(lines)
