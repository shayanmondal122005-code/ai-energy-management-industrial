"""Environmental suppression gate — shared by every intraday detector.

Irradiance is MODELED, not measured, so a passing cloud can look like a generation
fault. This gate decides SUPPRESS | DOWNWEIGHT | PASS using three layers:

  1) COHERENCE  — a fault is LOCALIZED (one string/inverter drops while peers hold);
                  if ALL units drop together the cause is environmental.
  2) PERSISTENCE— a real fault holds for > persist_minutes across >= K intervals;
                  cloud dips are transient and self-recover.
  3) FORECAST   — during high cloud_variability windows widen thresholds / DOWNWEIGHT;
                  during clear_sky windows keep thresholds tight (a deviation is real).

Soiling is EXEMPT (it runs on daily PR; intraday clouds average out) and is simply
never routed through this gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GateAction(str, Enum):
    SUPPRESS = "suppress"      # environmental — do not open a fault
    DOWNWEIGHT = "downweight"  # ambiguous — open with reduced confidence / wider threshold
    PASS = "pass"              # real — let the detector open the alert


@dataclass(frozen=True)
class GateConfig:
    persist_minutes: float = 20.0
    k_intervals: int = 2
    variability_threshold: float = 0.4   # cloud_variability_index above this = "variable"
    coherence_fraction: float = 0.8      # ≥ this share of units dropped ⇒ coherent
    drop_threshold: float = 0.08         # a unit is "dropped" beyond this fraction


@dataclass(frozen=True)
class GateContext:
    scope: str                          # 'string' | 'inverter' | 'plant'
    coherent: bool                      # all peers dropped together this interval
    localized: bool                     # confined to one unit while peers hold
    intervals_persisted: int
    minutes_persisted: float
    forecast_variability_index: float
    clear_sky: bool
    satellite_poa_dropped: bool         # modeled POA itself fell (a real cloud is present)


@dataclass(frozen=True)
class GateDecision:
    action: GateAction
    reason: str
    confidence_factor: float            # multiply detector confidence (1.0 = unchanged)


def environmental_gate(ctx: GateContext, cfg: GateConfig | None = None) -> GateDecision:
    cfg = cfg or GateConfig()

    # A single string dropping while peers hold can't be a cloud (clouds don't pick
    # one string). Always real.
    if ctx.localized:
        return GateDecision(GateAction.PASS, "localized to one unit — clouds don't hit one string", 1.0)

    persisted = (ctx.minutes_persisted >= cfg.persist_minutes
                 and ctx.intervals_persisted >= cfg.k_intervals)
    forecast_variable = ctx.forecast_variability_index >= cfg.variability_threshold

    # Persists beyond threshold despite stable/clear POA → real even if coherent.
    if persisted and (ctx.clear_sky or not ctx.satellite_poa_dropped):
        return GateDecision(GateAction.PASS, "persisted under stable/clear sky", 1.0)

    # Coherent transient dip during a variable / POA-dropped window → classic cloud.
    if ctx.coherent and (forecast_variable or ctx.satellite_poa_dropped) and not persisted:
        return GateDecision(GateAction.SUPPRESS,
                            "coherent transient dip during cloud/POA-drop window", 0.0)

    # Generally variable sky → don't trust tight thresholds; let it open but downweighted.
    if forecast_variable:
        return GateDecision(GateAction.DOWNWEIGHT, "high forecast cloud variability — widen thresholds", 0.5)

    # Sustained under stable sky → real.
    if persisted:
        return GateDecision(GateAction.PASS, "deviation persisted", 1.0)

    # Not yet persistent and no clear environmental cause → accrue more evidence.
    return GateDecision(GateAction.DOWNWEIGHT, "insufficient persistence — accruing evidence", 0.4)


def assess_coherence(drop_fractions: dict[str, float], cfg: GateConfig | None = None) -> tuple[bool, bool]:
    """From each peer unit's drop fraction (0 = normal, 1 = fully off) decide
    (coherent, localized). Coherent = most units dropped together; localized = a
    small minority dropped while the rest hold."""
    cfg = cfg or GateConfig()
    n = len(drop_fractions)
    if n == 0:
        return False, False
    dropped = [u for u, d in drop_fractions.items() if d >= cfg.drop_threshold]
    frac = len(dropped) / n
    coherent = frac >= cfg.coherence_fraction
    localized = 0 < len(dropped) <= max(1, n // 4) and not coherent
    return coherent, localized


def poa_dropped(actual_poa_wm2: float, clear_sky_poa_wm2: float, *, ratio: float = 0.85) -> bool:
    """Did modeled POA itself fall below the clear-sky expectation (a real cloud)?"""
    if clear_sky_poa_wm2 <= 0:
        return False
    return actual_poa_wm2 < ratio * clear_sky_poa_wm2
