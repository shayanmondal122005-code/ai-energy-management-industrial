"""EMS history integration — data-driven baseline + calibration from history."""
import math

from backend.services.solar_om.history import (
    baseline_deviation,
    calibrate_eta_bos_from_history,
    corroborated_loss,
    site_baseline_pr,
)
from backend.services.solar_om.models import Plant


def _plant():
    return Plant(id="P", name="t", lat=22.57, lon=88.36, tilt_deg=22, azimuth_deg=180,
                 rated_capacity_kwp=100.0)


class TestSiteBaselinePR:
    def test_uses_clean_clearsky_high_percentile(self):
        # 12 clear days around 0.84 clean + some soiled (0.7) days → baseline ~0.84, not dragged down.
        daily = [0.84, 0.85, 0.83, 0.70, 0.84, 0.85, 0.69, 0.84, 0.83, 0.85, 0.84, 0.83, 0.85, 0.84]
        clear = [True] * 14
        base = site_baseline_pr(daily, clear)
        assert base is not None and base >= 0.84

    def test_none_until_enough_days(self):
        assert site_baseline_pr([0.84, 0.85], [True, True]) is None

    def test_ignores_cloudy_days(self):
        daily = [0.84] * 12 + [0.5, 0.5]
        clear = [True] * 12 + [False, False]   # cloudy days excluded
        assert site_baseline_pr(daily, clear) >= 0.83


class TestCalibrationFromHistory:
    def test_recovers_eta_from_clean_days(self):
        ideal = [600.0] * 12
        actual = [0.82 * x for x in ideal]
        clear = [True] * 12
        eta = calibrate_eta_bos_from_history(_plant(), actual, ideal, clear)
        assert math.isclose(eta, 0.82, abs_tol=1e-3)

    def test_excludes_cloudy_days_from_fit(self):
        ideal = [600.0] * 12 + [600.0, 600.0]
        actual = [0.82 * 600] * 12 + [100.0, 90.0]   # cloudy outliers
        clear = [True] * 12 + [False, False]
        eta = calibrate_eta_bos_from_history(_plant(), actual, ideal, clear)
        assert math.isclose(eta, 0.82, abs_tol=1e-3)  # outliers ignored


class TestDeviationAndBlend:
    def test_baseline_deviation(self):
        assert math.isclose(baseline_deviation(0.756, 0.84), 0.1, abs_tol=1e-3)
        assert baseline_deviation(0.86, 0.84) == 0.0   # at/above baseline

    def test_corroborated_agreement_high_confidence(self):
        loss, conf = corroborated_loss(0.12, 0.13)
        assert conf >= 0.9 and 0.12 <= loss <= 0.13

    def test_corroborated_disagreement_conservative(self):
        loss, conf = corroborated_loss(0.20, 0.02)   # baselines disagree
        assert conf < 0.7 and loss == 0.02            # take the smaller, low confidence
