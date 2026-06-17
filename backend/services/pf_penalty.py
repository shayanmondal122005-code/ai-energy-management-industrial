"""Power-factor penalty + kVA-demand estimation for industrial tariffs.

Industrial electricity bills charge demand on kVA and penalise low power factor;
the existing savings engine (ToD energy + flat ₹/kW demand) models neither. These
pure helpers quantify the PF penalty a site currently pays — an avoidable cost
that PF correction (capacitor bank or battery reactive support) removes — and the
extra demand charge low PF causes when demand is billed on kVA.

Pure functions (no DB / framework) so they unit-test without a database.

NOTE: PF-penalty slabs vary by DISCOM tariff order. The model here is the common
"X% of charges per 0.01 of PF below a threshold" form; confirm the threshold and
rate against the customer's actual tariff before quoting.
"""
import math


def apparent_kva(real_kw: float, pf: float) -> float:
    """kVA the grid must supply to deliver real_kw at power factor pf."""
    pf = max(0.01, min(1.0, pf))
    return real_kw / pf


def reactive_kvar(real_kw: float, pf: float) -> float:
    """Reactive power (kVAr) for real_kw at pf — what a capacitor bank must offset."""
    pf = max(0.01, min(1.0, pf))
    return real_kw * math.tan(math.acos(pf))


def pf_penalty_rs(
    measured_pf: float,
    billable_charges_rs: float,
    *,
    threshold: float = 0.95,
    penalty_pct_per_point: float = 1.0,
) -> float:
    """Monthly PF penalty (₹): penalty_pct_per_point % of billable_charges for each
    0.01 the PF sits below `threshold`. 0 if PF >= threshold. This is the avoidable
    amount PF correction would save."""
    if measured_pf >= threshold:
        return 0.0
    points = round((threshold - measured_pf) / 0.01)
    pct = points * penalty_pct_per_point
    return round(billable_charges_rs * pct / 100.0, 2)


def kva_demand_charge_rs(peak_kw: float, pf: float, demand_per_kva: float) -> float:
    """Demand charge when billed on kVA — low PF inflates the kVA, so this rises as
    PF falls even for the same real-power peak."""
    return round(apparent_kva(peak_kw, pf) * demand_per_kva, 2)


def pf_penalty_from_tariff(measured_pf: float, billable_charges_rs: float, tariff: dict) -> float:
    """PF penalty using a tariff dict's `pf_threshold` / `pf_penalty_pct` (with sane
    defaults if absent)."""
    return pf_penalty_rs(
        measured_pf,
        billable_charges_rs,
        threshold=float(tariff.get("pf_threshold", 0.95)),
        penalty_pct_per_point=float(tariff.get("pf_penalty_pct", 1.0)),
    )
