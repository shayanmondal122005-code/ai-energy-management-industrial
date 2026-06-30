"""Environmental gate — the false-alarm killer. cloud_pass MUST be suppressed."""
from backend.services.solar_om.gate import (
    GateAction,
    GateConfig,
    GateContext,
    assess_coherence,
    environmental_gate,
    poa_dropped,
)


def _ctx(**kw):
    base = dict(scope="inverter", coherent=False, localized=False,
                intervals_persisted=1, minutes_persisted=5.0,
                forecast_variability_index=0.05, clear_sky=True,
                satellite_poa_dropped=False)
    base.update(kw)
    return GateContext(**base)


class TestCloudPassSuppressed:
    def test_coherent_transient_cloud_is_suppressed(self):
        # All units drop together, forecast says variable, only a few minutes → cloud.
        d = environmental_gate(_ctx(
            coherent=True, forecast_variability_index=0.7, clear_sky=False,
            satellite_poa_dropped=True, minutes_persisted=5.0, intervals_persisted=1,
        ))
        assert d.action == GateAction.SUPPRESS

    def test_coherent_dip_with_poa_drop_suppressed_even_if_forecast_calm(self):
        d = environmental_gate(_ctx(
            coherent=True, forecast_variability_index=0.1, clear_sky=False,
            satellite_poa_dropped=True, minutes_persisted=10.0, intervals_persisted=1,
        ))
        assert d.action == GateAction.SUPPRESS


class TestRealFaultsPass:
    def test_localized_single_string_passes(self):
        # One string drops while peers hold — clouds can't do that.
        d = environmental_gate(_ctx(scope="string", localized=True, coherent=False))
        assert d.action == GateAction.PASS

    def test_persistent_outage_under_clear_sky_passes(self):
        # Coherent drop BUT it persists for 30 min under a clear sky → real (e.g. fleet outage).
        d = environmental_gate(_ctx(
            coherent=True, clear_sky=True, satellite_poa_dropped=False,
            minutes_persisted=30.0, intervals_persisted=3, forecast_variability_index=0.05,
        ))
        assert d.action == GateAction.PASS

    def test_persists_despite_being_coherent_when_poa_stable(self):
        d = environmental_gate(_ctx(
            coherent=True, clear_sky=False, satellite_poa_dropped=False,
            minutes_persisted=40.0, intervals_persisted=4,
        ))
        assert d.action == GateAction.PASS


class TestDownweight:
    def test_variable_window_downweights(self):
        d = environmental_gate(_ctx(
            coherent=False, forecast_variability_index=0.6,
            minutes_persisted=10.0, intervals_persisted=1, clear_sky=False,
        ))
        assert d.action == GateAction.DOWNWEIGHT
        assert d.confidence_factor < 1.0


class TestCoherenceHelper:
    def test_all_drop_is_coherent(self):
        coherent, localized = assess_coherence({"a": 0.4, "b": 0.45, "c": 0.42, "d": 0.4})
        assert coherent and not localized

    def test_one_drop_is_localized(self):
        coherent, localized = assess_coherence({"a": 0.0, "b": 0.0, "c": 0.0, "d": 0.5})
        assert localized and not coherent

    def test_poa_dropped_helper(self):
        assert poa_dropped(400, 800) is True          # half of clear sky → cloud
        assert poa_dropped(780, 800) is False         # within 85% → clear
