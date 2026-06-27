"""Power-factor advisory + monitoring — the EMS's PF intelligence layer.

PF is corrected by HARDWARE (a capacitor bank — often DISCOM-mandated — or a
4-quadrant inverter). The EMS does NOT correct PF by itself. This module is the
brains around that hardware:
  • quantify the PF cost (a separate penalty OR the kVAh-billing premium),
  • size the capacitor bank needed to reach a target PF,
  • monitor PF and flag when correction has degraded (a capacitor bank silently
    failing quietly restores the penalty — this catches it),
  • (GATED, disabled by default) compute a reactive setpoint ONLY when a
    4-quadrant inverter is present.

Pure functions — no DB/framework — so they unit-test without a database.
"""
import math
from dataclasses import dataclass

DEFAULT_TARGET_PF = 0.99   # capacitor banks routinely reach ~0.99


def _tan_phi(pf: float) -> float:
    pf = max(0.01, min(1.0, pf))
    return math.tan(math.acos(pf))


def capacitor_kvar_required(load_kw: float, pf_now: float, pf_target: float = DEFAULT_TARGET_PF) -> float:
    """kVAr of capacitors (or inverter reactive support) to lift PF from pf_now to
    pf_target at a given real load.  kVAr = kW × (tan φ_now − tan φ_target)."""
    need = float(load_kw) * (_tan_phi(pf_now) - _tan_phi(pf_target))
    return round(max(0.0, need), 1)


def kvah_pf_premium_rs(energy_kwh: float, rate_per_unit: float, pf_now: float, pf_target: float = 1.0) -> float:
    """For kVAh-billed tariffs (e.g. Jharkhand HT): the ₹ overpaid because energy is
    billed on apparent (kVAh) rather than real (kWh). Returns the saving from
    correcting pf_now → pf_target."""
    pf_now = max(0.01, min(1.0, pf_now))
    pf_target = max(0.01, min(1.0, pf_target))
    return round(energy_kwh * rate_per_unit * (1.0 / pf_now - 1.0 / pf_target), 2)


def pf_health(pf_now: float, pf_target: float = 0.95, warn_band: float = 0.02) -> tuple[str, float]:
    """Monitoring: is the installed PF correction still working?
    Returns (status, deviation): 'ok' | 'warning' | 'critical'.
    'critical' means the correction has likely failed (blown capacitor fuse), which
    silently restores the penalty/kVAh premium — alert the operator."""
    dev = round(pf_target - pf_now, 3)
    if pf_now >= pf_target:
        return "ok", dev
    if pf_now >= pf_target - warn_band:
        return "warning", dev
    return "critical", dev


@dataclass
class PfAdvice:
    pf_now: float
    pf_target: float
    capacitor_kvar: float                  # recommended bank size to install
    health_status: str                     # ok | warning | critical
    control_mode: str                      # "advisory" | "reactive_inverter"
    reactive_setpoint_kvar: float | None   # set ONLY when a 4-quadrant inverter is present


def pf_advice(
    load_kw: float,
    pf_now: float,
    *,
    pf_target: float = DEFAULT_TARGET_PF,
    reactive_capable: bool = False,        # GATED: disabled by default
) -> PfAdvice:
    """Top-level PF recommendation. control_mode is 'reactive_inverter' ONLY when a
    4-quadrant inverter is confirmed present (reactive_capable=True); otherwise it is
    'advisory' (size + monitor a capacitor bank) and NO control setpoint is emitted —
    we never send a reactive command to hardware that can't accept it."""
    kvar = capacitor_kvar_required(load_kw, pf_now, pf_target)
    status, _ = pf_health(pf_now, pf_target)
    if reactive_capable:
        return PfAdvice(pf_now, pf_target, kvar, status, "reactive_inverter", kvar)
    return PfAdvice(pf_now, pf_target, kvar, status, "advisory", None)
