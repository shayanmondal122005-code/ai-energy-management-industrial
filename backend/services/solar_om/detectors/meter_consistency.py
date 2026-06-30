"""Meter ↔ inverter consistency — the merge's free cross-check.

In the merged EMS + O&M system the same plant has TWO solar feeds on one RS485 bus:
the revenue-grade solar METER (plant total, accurate kWh) and the INVERTER (per-string
detail + self-reported AC). They measure the same total at different fidelity, so a
PERSISTENT gap between meter-total and summed-inverter AC is itself a signal:

  • inverter_sum << meter  → an inverter is under-reporting / a comms or mapping gap
                             (the meter sees generation the inverter feed is missing)
  • inverter_sum >> meter  → meter / CT calibration problem (rare; flag for inspection)

This is a DATA-INTEGRITY detector (not a generation loss): the meter stays the source
of truth for ₹/ROI, the inverter for fault detection — this guards that both agree.
"""
from __future__ import annotations

from backend.services.solar_om.models import AlertDraft, Severity

THETA_DIVERGENCE = 0.05   # >5% disagreement between the two solar feeds


def detect_meter_inverter_divergence(
    plant_id: str, meter_kwh: float, inverter_sum_kwh: float,
    *, theta: float = THETA_DIVERGENCE, min_kwh: float = 10.0,
) -> AlertDraft | None:
    """Compare the revenue meter's plant total to the summed inverter AC over the same
    window. `min_kwh` skips windows with too little generation to compare meaningfully."""
    if meter_kwh < min_kwh:
        return None
    gap = (meter_kwh - inverter_sum_kwh) / meter_kwh
    if abs(gap) <= theta:
        return None

    if gap > 0:   # meter sees more than the inverters reported
        action = ("Inverter feed under-reports vs the revenue meter — check inverter comms, "
                  "Modbus register map, or an inverter dropped from the gateway")
    else:         # inverters report more than the meter
        action = ("Inverter feed exceeds the revenue meter — check meter/CT calibration "
                  "and wiring before trusting either total")
    return AlertDraft(
        plant_id=plant_id, type="meter_inverter_divergence",
        severity=Severity.INVESTIGATE,
        recommended_action=action,
        confidence=min(1.0, 0.6 + abs(gap)),
        evidence={
            "divergence_pct": round(gap * 100, 1),
            "meter_kwh": round(meter_kwh, 1),
            "inverter_sum_kwh": round(inverter_sum_kwh, 1),
        },
    )
