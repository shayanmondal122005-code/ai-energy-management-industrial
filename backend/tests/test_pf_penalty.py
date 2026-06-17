"""Tests for power-factor penalty + kVA-demand helpers."""
import math

from backend.services.pf_penalty import (
    apparent_kva, kva_demand_charge_rs, pf_penalty_from_tariff, pf_penalty_rs, reactive_kvar,
)


class TestPowerFactor:

    def test_apparent_kva(self):
        assert apparent_kva(100, 0.8) == 125.0      # 100kW / 0.8 = 125 kVA
        assert apparent_kva(100, 1.0) == 100.0

    def test_reactive_kvar(self):
        # 100kW @ 0.8 PF -> tan(acos(0.8)) = 0.75 -> 75 kVAr
        assert math.isclose(reactive_kvar(100, 0.8), 75.0, abs_tol=0.01)

    def test_no_penalty_at_or_above_threshold(self):
        assert pf_penalty_rs(0.95, 100000, threshold=0.95, penalty_pct_per_point=1.0) == 0.0
        assert pf_penalty_rs(0.98, 100000, threshold=0.95) == 0.0

    def test_penalty_scales_with_points_below(self):
        # 0.90 vs 0.95 threshold = 5 points * 1% = 5% of 100000 = 5000
        assert pf_penalty_rs(0.90, 100000, threshold=0.95, penalty_pct_per_point=1.0) == 5000.0

    def test_kva_demand_rises_as_pf_falls(self):
        good = kva_demand_charge_rs(peak_kw=400, pf=0.98, demand_per_kva=350)
        poor = kva_demand_charge_rs(peak_kw=400, pf=0.80, demand_per_kva=350)
        assert poor > good

    def test_from_tariff_uses_tariff_rules(self):
        tariff = {"pf_threshold": 0.90, "pf_penalty_pct": 2.0}
        # 0.85 vs 0.90 = 5 points * 2% = 10% of 50000 = 5000
        assert pf_penalty_from_tariff(0.85, 50000, tariff) == 5000.0
