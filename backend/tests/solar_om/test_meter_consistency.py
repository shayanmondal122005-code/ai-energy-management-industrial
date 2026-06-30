"""Meter ↔ inverter consistency detector (the merge cross-check)."""
from backend.services.solar_om.detectors.meter_consistency import detect_meter_inverter_divergence
from backend.services.solar_om.models import Severity


class TestMeterDivergence:
    def test_agreement_no_alert(self):
        # Inverters within 2% of the meter → fine.
        assert detect_meter_inverter_divergence("P1", meter_kwh=500.0, inverter_sum_kwh=492.0) is None

    def test_inverter_under_reports(self):
        d = detect_meter_inverter_divergence("P1", meter_kwh=500.0, inverter_sum_kwh=440.0)
        assert d is not None and d.severity == Severity.INVESTIGATE
        assert d.evidence["divergence_pct"] == 12.0
        assert "under-report" in d.recommended_action

    def test_meter_under_reads(self):
        d = detect_meter_inverter_divergence("P1", meter_kwh=440.0, inverter_sum_kwh=500.0)
        assert d is not None and "meter/CT" in d.recommended_action

    def test_skips_low_generation_window(self):
        # Too little energy to compare meaningfully.
        assert detect_meter_inverter_divergence("P1", meter_kwh=3.0, inverter_sum_kwh=1.0) is None


class TestEngineWrapper:
    def test_opens_then_closes_via_store(self):
        from datetime import datetime, timezone

        from backend.services.solar_om.detectors.base import InMemoryAlertStore
        from backend.services.solar_om.engine import run_meter_consistency
        from backend.services.solar_om.models import Plant

        plant = Plant(id="P1", name="t", lat=22.57, lon=88.36, tilt_deg=22, azimuth_deg=180,
                      rated_capacity_kwp=100.0, eta_bos=0.83)
        store = InMemoryAlertStore()
        ts = datetime(2024, 3, 15, tzinfo=timezone.utc)
        run_meter_consistency(plant, meter_kwh=500.0, inverter_sum_kwh=440.0, store=store, ts=ts)
        assert len(store.open_by_type("meter_inverter_divergence")) == 1
        # Feeds agree next run → alert closes.
        run_meter_consistency(plant, meter_kwh=500.0, inverter_sum_kwh=495.0, store=store, ts=ts)
        assert store.open_by_type("meter_inverter_divergence") == []
