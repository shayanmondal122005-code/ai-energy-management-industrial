"""End-to-end scenarios — the acceptance criteria.

Each scenario seeds a day of mock readings + matching env/forecast, runs the engine,
and asserts the alert outcome:
  clean        → ZERO alerts
  cloud_pass   → ZERO alerts, logged as status=suppressed (the gate did its job)
  soiling      → soiling alert; a cleaning event closes it with a recovery report
  outage       → critical inverter_outage with ₹ impact
  dead_string  → string fault (open circuit)
  ground_fault → Tier-1.5 critical
  riso_decline → Tier-1.5 insulation-trend investigate
"""
from datetime import timedelta

from backend.services.solar_om.detectors.base import InMemoryAlertStore
from backend.services.solar_om.engine import run_intraday, run_trends, site_health, verify_recovery
from backend.services.solar_om.models import AlertStatus, Severity
from backend.services.solar_om.seed import build_scenario


def _run(name):
    sc = build_scenario(name)
    store = InMemoryAlertStore()
    run_intraday(sc.plant, sc.inverters, sc.strings, sc.intervals, sc.engine_env,
                 sc.forecast, sc.tariff, store)
    if sc.pr_tcorr_series or sc.weekly_riso_by_inverter:
        run_trends(sc.plant, sc.inverters, store,
                   pr_tcorr_series=sc.pr_tcorr_series, days_since_clean=sc.days_since_clean,
                   expected_kwh_day=sc.expected_kwh_day, tariff_rate=6.10,
                   cleaning_cost=sc.cleaning_cost,
                   weekly_riso_by_inverter=sc.weekly_riso_by_inverter,
                   ts=sc.intervals[-1][0].ts)
    return sc, store


class TestCleanAndCloud:
    def test_clean_produces_zero_alerts(self):
        _sc, store = _run("clean")
        assert store.open_alerts() == []
        assert store.suppressed() == []

    def test_cloud_pass_is_suppressed_not_alerted(self):
        _sc, store = _run("cloud_pass")
        # The crux: ZERO open alerts, and the dip is logged as suppressed for audit.
        assert store.open_alerts() == []
        assert len(store.suppressed()) >= 1
        assert all(s["status"] == AlertStatus.SUPPRESSED for s in store.suppressed())


class TestGenerationLossDetectors:
    def test_outage_is_critical_with_rupees(self):
        _sc, store = _run("outage")
        outages = store.open_by_type("inverter_outage")
        assert len(outages) == 1
        assert outages[0]["severity"] == Severity.CRITICAL
        assert outages[0]["rupee_impact_per_day"] > 0
        # A dead inverter is an outage, NOT also a derate (root-cause dedupe).
        assert store.open_by_type("inverter_derate") == []

    def test_dead_string_flags_open_circuit(self):
        _sc, store = _run("dead_string")
        string_alerts = store.open_by_type("string_open")
        assert len(string_alerts) >= 1
        assert string_alerts[0]["severity"] == Severity.CRITICAL
        # string_open supersedes the generic underperformance + inverter derate.
        assert store.open_by_type("string_underperformance") == []
        assert store.open_by_type("inverter_derate") == []


class TestSafety:
    def test_ground_fault_is_critical(self):
        _sc, store = _run("ground_fault")
        gf = store.open_by_type("ground_fault")
        assert len(gf) == 1 and gf[0]["severity"] == Severity.CRITICAL
        assert gf[0]["risk_note"]

    def test_riso_decline_opens_investigate(self):
        _sc, store = _run("riso_decline")
        rt = store.open_by_type("insulation_trend")
        assert len(rt) == 1 and rt[0]["severity"] == Severity.INVESTIGATE


class TestSoilingAndRecovery:
    def test_soiling_alerts_then_cleaning_closes_with_recovery_report(self):
        sc, store = _run("soiling")
        soil = store.open_by_type("soiling")
        assert len(soil) == 1
        key = (sc.plant.id, None, None, "soiling")

        # Operator logs a cleaning event → move to verifying.
        ev_ts = sc.intervals[-1][0].ts + timedelta(days=1)
        assert store.move_to_verifying(key, ev_ts) is True

        # After the wash, PR_tcorr steps back up → verify recovery, close, emit M&V report.
        before = sc.pr_tcorr_series[-1]
        after = sc.pr_tcorr_series[0]  # back to the as-clean level
        report = verify_recovery(store, key, ev_ts, pr_tcorr_before=before,
                                 pr_tcorr_after=after, expected_kwh_day=sc.expected_kwh_day,
                                 tariff_rate=6.10)
        assert report is not None
        assert report["rupee_recovered_per_day"] > 0
        assert store.open_by_type("soiling") == []
        closed = store.closed()[0]
        assert closed["status"] == AlertStatus.RESOLVED
        assert closed["recovery"]["kwh_regained_per_day"] > 0


class TestHealth:
    def test_site_health_totals_rupees(self):
        _sc, store = _run("outage")
        h = site_health(_sc if False else build_scenario("outage").plant, store)
        assert h["open_alerts"] >= 1
        assert h["total_rupee_impact_per_day"] > 0
