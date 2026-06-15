"""Bridge edge-device telemetry into facility `readings`.

The edge path (`/api/v1/ingest`) stores watt-scale telemetry in the `telemetry`
table keyed by site_id. Facility features — shadow-savings, history charts —
read the kW-scale `readings` table keyed by facility_id. This maps one sample
from the first shape to the second so a real meter feeds BOTH.

Pure function (no DB / framework imports) so it unit-tests without a database.
"""


def telemetry_to_reading(total_load_w, solar_w, soc_pct) -> dict:
    """Map one edge telemetry sample (watts, %) → a `readings` row (kW).

    grid_kw is the net import (load − solar) floored at 0 — a meter-only shadow
    site imports whatever the load is after on-site solar; export is reported as
    a negative net_kw but never as negative grid import.
    """
    load_kw  = (total_load_w or 0.0) / 1000.0
    solar_kw = (solar_w or 0.0) / 1000.0
    net_kw   = load_kw - solar_kw
    return {
        "load_kw":     round(load_kw, 3),
        "solar_kw":    round(solar_kw, 3),
        "battery_soc": float(soc_pct or 0.0),
        "grid_kw":     round(max(0.0, net_kw), 3),
        "net_kw":      round(net_kw, 3),
    }
