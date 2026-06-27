"""Safety/fail-safe tests for optimize_dispatch_v2 — input validation,
sanctioned grid-import limit, and SoC banding. These guard the hard,
non-negotiable physical constraints."""
from backend.services.optimizer_v2 import _validate_inputs, optimize_dispatch_v2

FLAT = [6.0] * 24


class TestInputValidation:
    """Bad/missing input must return a fail-safe 'no action', never an unsafe state."""

    def test_wrong_length_returns_noop(self):
        s = optimize_dispatch_v2([100.0] * 23, [0.0] * 24, FLAT, 0.5)
        assert s.status.startswith("invalid_input")
        assert max(s.discharge_kw) == 0 and max(s.charge_kw) == 0 and max(s.grid_kw) == 0

    def test_negative_load_rejected(self):
        load = [100.0] * 24
        load[5] = -10.0
        assert optimize_dispatch_v2(load, [0.0] * 24, FLAT, 0.5).status.startswith("invalid_input")

    def test_soc_out_of_range_rejected(self):
        assert optimize_dispatch_v2([100.0] * 24, [0.0] * 24, FLAT, 1.5).status.startswith("invalid_input")

    def test_nonfinite_rejected(self):
        load = [100.0] * 24
        load[3] = float("nan")
        assert optimize_dispatch_v2(load, [0.0] * 24, FLAT, 0.5).status.startswith("invalid_input")

    def test_valid_inputs_pass(self):
        assert _validate_inputs([100.0] * 24, [0.0] * 24, FLAT, 0.5, 500) is None


class TestSafetyLimits:

    def test_grid_import_capped_at_sanctioned_limit(self):
        load = [100.0] * 24
        load[19] = 350.0                       # one evening spike above the cap
        s = optimize_dispatch_v2(
            load, [0.0] * 24, FLAT, current_soc=0.6, battery_kwh=500,
            max_charge_kw=250, max_discharge_kw=250, min_soc=0.2, max_soc=0.9,
            max_grid_kw=200.0,
        )
        assert s.status == "optimal"
        assert max(s.grid_kw) <= 200.0 + 0.5       # sanctioned import respected
        assert max(s.discharge_kw) <= 250.0 + 0.5  # inverter rating respected

    def test_soc_stays_within_band(self):
        s = optimize_dispatch_v2(
            [200.0] * 24, [0.0] * 24, FLAT, current_soc=0.5, battery_kwh=500,
            min_soc=0.2, max_soc=0.9,
        )
        assert min(s.soc_trace) >= 20.0 - 0.5
        assert max(s.soc_trace) <= 90.0 + 0.5
