"""Scenario seeding — a day of mock readings + matching mock env/forecast.

`build_scenario(name)` returns everything the engine needs for one scenario so the
acceptance test (and a CLI `seed --scenario …`) can drive the full pipeline. The
mock inverter source is fed by a "reality" environment (which may contain a cloud);
the engine is given the SATELLITE environment (the server-side model) separately —
in cloud_pass the satellite is clear while reality is clouded, exactly the missed-
cloud case the gate must suppress.

Scenarios: clean | soiling | outage | dead_string | cloud_pass | ground_fault | riso_decline
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from backend.services.solar_om.environment import MockEnvironment
from backend.services.solar_om.forecast import MockForecast
from backend.services.solar_om.inverter_source import MockFaults, MockInverterSource
from backend.services.solar_om.models import ForecastWindow, Inverter, Plant, Reading, StringSpec
from backend.services.solar_om.tariff import Tariff

IST = timezone(timedelta(hours=5, minutes=30))
SCENARIOS = ["clean", "soiling", "outage", "dead_string", "cloud_pass", "ground_fault", "riso_decline"]


@dataclass
class Scenario:
    name: str
    plant: Plant
    inverters: list[Inverter]
    strings: list[StringSpec]
    intervals: list[list[Reading]]
    engine_env: MockEnvironment          # SATELLITE model the engine compares against
    forecast: ForecastWindow
    tariff: Tariff
    interval_hours: float = 0.25
    # trend inputs (soiling / riso_decline)
    pr_tcorr_series: list[float] | None = None
    days_since_clean: int = 0
    expected_kwh_day: float = 480.0
    cleaning_cost: float = 3000.0
    weekly_riso_by_inverter: dict[str, list[float]] = field(default_factory=dict)


def _plant() -> Plant:
    return Plant(id="PLANT-001", name="Demo 100kWp", lat=22.57, lon=88.36,
                 tilt_deg=22.0, azimuth_deg=180.0, rated_capacity_kwp=100.0,
                 module_temp_coeff=-0.0035, noct_c=45.0, eta_bos=0.83,
                 tariff_id="cesc", commissioned_at=datetime(2025, 1, 1, tzinfo=IST))


def _topology():
    invs = [Inverter(id="INV1", plant_id="PLANT-001", rated_kw=50, modbus_slave_id=1,
                     riso_threshold_kohm=600),
            Inverter(id="INV2", plant_id="PLANT-001", rated_kw=50, modbus_slave_id=2,
                     riso_threshold_kohm=600)]
    strs = [StringSpec(id="S1a", inverter_id="INV1", mppt_index=1, rated_share_fraction=0.25),
            StringSpec(id="S1b", inverter_id="INV1", mppt_index=2, rated_share_fraction=0.25),
            StringSpec(id="S2a", inverter_id="INV2", mppt_index=1, rated_share_fraction=0.25),
            StringSpec(id="S2b", inverter_id="INV2", mppt_index=2, rated_share_fraction=0.25)]
    return invs, strs


def _timestamps(day: datetime) -> list[datetime]:
    """15-min cadence over the productive window 08:00–16:00 IST."""
    start = day.replace(hour=8, minute=0, second=0, microsecond=0)
    return [start + timedelta(minutes=15 * i) for i in range(33)]


def _cesc_tariff() -> Tariff:
    return Tariff.from_tod(cheap=4.20, normal=6.10, peak=7.85,
                           cheap_hours=range(10, 16), peak_hours=range(18, 23),
                           id="cesc", name="West Bengal - CESC")


def build_scenario(name: str, day: datetime | None = None) -> Scenario:
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario {name!r}; choose from {SCENARIOS}")
    day = day or datetime(2026, 6, 29, tzinfo=IST)
    plant = _plant()
    invs, strs = _topology()
    timestamps = _timestamps(day)
    tariff = _cesc_tariff()

    satellite = MockEnvironment(clear_sky_peak_ghi=900.0, ambient_c=30.0)  # the engine's model
    reality = satellite                                                    # reality == model by default
    faults = MockFaults()
    forecast_variable = False
    pr_series = None
    days_since_clean = 0
    weekly_riso: dict[str, list[float]] = {}

    if name == "soiling":
        faults = MockFaults(soiling_loss_frac=0.07)        # uniform, sub-threshold intraday
        days_since_clean = 14
        pr_series = [0.83 - 0.004 * d for d in range(14)]  # daily PR_tcorr decline
    elif name == "outage":
        faults = MockFaults(outage_inverters={"INV1"})     # one inverter dead all day
    elif name == "dead_string":
        faults = MockFaults(open_circuit_strings={"S1a"})  # I≈0, V present
    elif name == "cloud_pass":
        # Reality clouds the LAST interval; the satellite model stays clear (missed it).
        reality = MockEnvironment(clear_sky_peak_ghi=900.0, ambient_c=30.0,
                                  cloud_intervals={timestamps[-1]}, cloud_factor=0.25)
        forecast_variable = True
    elif name == "ground_fault":
        faults = MockFaults(ground_fault_inverters={"INV1"})
    elif name == "riso_decline":
        weekly_riso = {"INV1": [900, 820, 760, 700]}       # above threshold but falling

    src = MockInverterSource(plant, invs, strs, reality, faults=faults)
    intervals = [src.read(ts) for ts in timestamps]

    forecast = MockForecast(peak_ghi=900.0, variable=forecast_variable).get(plant, timestamps[0], 24)

    return Scenario(
        name=name, plant=plant, inverters=invs, strings=strs, intervals=intervals,
        engine_env=satellite, forecast=forecast, tariff=tariff,
        pr_tcorr_series=pr_series, days_since_clean=days_since_clean,
        weekly_riso_by_inverter=weekly_riso,
    )
