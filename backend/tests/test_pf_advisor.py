"""Tests for the PF advisory + monitoring module."""
import math

from backend.services.pf_advisor import (
    capacitor_kvar_required, kvah_pf_premium_rs, pf_advice, pf_health,
)


class TestCapacitorSizing:
    def test_kvar_to_correct(self):
        # 100 kW at 0.80 PF -> 0.99 PF: 100*(tan(acos .8) - tan(acos .99)) ≈ 60.7 kVAr
        kvar = capacitor_kvar_required(100, 0.80, 0.99)
        assert math.isclose(kvar, 60.7, abs_tol=0.3)

    def test_no_correction_when_already_good(self):
        assert capacitor_kvar_required(100, 0.99, 0.99) == 0.0
        assert capacitor_kvar_required(100, 1.0, 0.99) == 0.0


class TestKvahPremium:
    def test_premium_from_low_pf(self):
        # 1000 kWh @ Rs6.40/kVAh, 0.85 -> 1.0 : 6400*(1/0.85 - 1) ≈ Rs1129
        assert math.isclose(kvah_pf_premium_rs(1000, 6.40, 0.85, 1.0), 1129.4, abs_tol=2.0)

    def test_zero_at_unity(self):
        assert kvah_pf_premium_rs(1000, 6.40, 1.0, 1.0) == 0.0


class TestPfHealth:
    def test_ok_at_or_above_target(self):
        assert pf_health(0.96, 0.95)[0] == "ok"

    def test_warning_just_below(self):
        assert pf_health(0.94, 0.95)[0] == "warning"      # within warn band

    def test_critical_far_below(self):
        assert pf_health(0.88, 0.95)[0] == "critical"     # correction likely failed


class TestPfAdviceGating:
    def test_advisory_by_default_no_command(self):
        a = pf_advice(400, 0.85)
        assert a.control_mode == "advisory"
        assert a.reactive_setpoint_kvar is None            # NEVER commands without capable inverter
        assert a.capacitor_kvar > 0

    def test_reactive_control_only_when_capable(self):
        a = pf_advice(400, 0.85, reactive_capable=True)
        assert a.control_mode == "reactive_inverter"
        assert a.reactive_setpoint_kvar is not None
        assert math.isclose(a.reactive_setpoint_kvar, a.capacitor_kvar, abs_tol=0.1)
