"""Inverter data sources.

- GatewaySource   : fed by POST /ingest (the ESP32 gateway contract).
- CloudApiSource  : stub for pulling from a vendor cloud API when the site already
                    exposes one — note: this lets a site skip the gateway entirely.
- MockInverterSource : a physically-consistent CLEAN baseline (actual ≈ expected×PR)
                    with INJECTABLE faults + cloud events, for tests and `seed`.

The gateway never sends irradiance/temperature; the server attaches env at read time
(EnvironmentSource), so MockInverterSource takes an EnvironmentSource to stay
consistent with the baseline the detectors compare against.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from backend.services.solar_om.baseline import expected_power_w
from backend.services.solar_om.environment import EnvironmentSource
from backend.services.solar_om.models import Inverter, Plant, Reading, StringSpec

NOMINAL_DC_VOLTAGE = 620.0
INV_DC_AC_EFF = 0.98


class InverterSource(ABC):
    @abstractmethod
    def read(self, ts: datetime) -> list[Reading]:
        """All readings (inverter-level + per-string) at this interval."""
        ...


class GatewaySource(InverterSource):
    """Replays readings already ingested via POST /ingest (buffered by ts)."""
    def __init__(self):
        self._by_ts: dict[datetime, list[Reading]] = {}

    def ingest(self, ts: datetime, readings: list[Reading]) -> None:
        self._by_ts.setdefault(ts, []).extend(readings)

    def read(self, ts: datetime) -> list[Reading]:
        return list(self._by_ts.get(ts, []))


class CloudApiSource(InverterSource):
    """STUB: pull readings from a vendor cloud API (SolarEdge/Sungrow/Huawei).

    When a site already streams to a vendor cloud, this source can replace the
    on-site gateway entirely — no ESP32 needed. Wire per-vendor auth + field map.
    """
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url
        self.api_key = api_key

    def read(self, ts: datetime) -> list[Reading]:  # pragma: no cover - stub
        raise NotImplementedError("CloudApiSource: wire the vendor cloud API client")


@dataclass
class MockFaults:
    """Knobs the scenarios flip. Defaults = perfectly clean."""
    soiling_loss_frac: float = 0.0                      # uniform multiplicative loss (0..1)
    string_current_factor: dict[str, float] = field(default_factory=dict)  # id → 0..1
    open_circuit_strings: set[str] = field(default_factory=set)            # I≈0, V present
    outage_inverters: set[str] = field(default_factory=set)               # ac_power≈0
    derate_inverter_factor: dict[str, float] = field(default_factory=dict)  # id → 0..1 cap
    clock_shading: dict[str, set[int]] = field(default_factory=dict)       # string id → hours
    riso_kohm: dict[str, float] = field(default_factory=dict)             # inverter id → kΩ
    ground_fault_inverters: set[str] = field(default_factory=set)
    arc_fault_inverters: set[str] = field(default_factory=set)
    recurring_fault_code: dict[str, int] = field(default_factory=dict)     # inverter id → code


class MockInverterSource(InverterSource):
    def __init__(self, plant: Plant, inverters: list[Inverter], strings: list[StringSpec],
                 env: EnvironmentSource, *, base_pr: float = 1.0,
                 faults: MockFaults | None = None):
        self.plant = plant
        self.inverters = inverters
        self.strings = strings
        self.env = env
        self.base_pr = base_pr
        self.faults = faults or MockFaults()
        self._cum_energy: dict[str, float] = {inv.id: 0.0 for inv in inverters}

    def _strings_of(self, inverter_id: str) -> list[StringSpec]:
        return [s for s in self.strings if s.inverter_id == inverter_id]

    def read(self, ts: datetime) -> list[Reading]:
        env = self.env.get(self.plant, ts)
        plant_expected_w = expected_power_w(self.plant, env)  # at eta=plant.eta_bos or 1
        f = self.faults
        out: list[Reading] = []

        for inv in self.inverters:
            inv_ac_w = 0.0
            inv_strings = self._strings_of(inv.id)
            for st in inv_strings:
                # Clean expected for this string, then apply faults.
                exp_w = plant_expected_w * st.rated_share_fraction * self.base_pr
                exp_w *= (1.0 - f.soiling_loss_frac)
                factor = f.string_current_factor.get(st.id, 1.0)
                if st.id in f.clock_shading and ts.hour in f.clock_shading[st.id]:
                    factor *= 0.5  # daily clock-locked dip (shading signature)
                dc_v = NOMINAL_DC_VOLTAGE if exp_w > 0 else 0.0
                if st.id in f.open_circuit_strings:
                    dc_i = 0.0                      # broken: no current, voltage still present
                    dc_v = NOMINAL_DC_VOLTAGE if env.poa_wm2 > 0 else 0.0
                else:
                    dc_power = max(0.0, exp_w * factor)
                    dc_i = (dc_power / dc_v) if dc_v > 0 else 0.0
                inv_ac_w += dc_v * dc_i * INV_DC_AC_EFF
                out.append(Reading(ts=ts, inverter_id=inv.id, string_id=st.id,
                                   dc_voltage=round(dc_v, 1), dc_current=round(dc_i, 2),
                                   ac_power_w=None))

            # Inverter-level overrides
            if inv.id in f.outage_inverters:
                inv_ac_w = 0.0
            if inv.id in f.derate_inverter_factor:
                inv_ac_w *= f.derate_inverter_factor[inv.id]

            self._cum_energy[inv.id] += inv_ac_w / 1000.0 / 4.0  # assume 15-min cadence
            fault_codes = []
            if inv.id in f.recurring_fault_code:
                fault_codes = [f.recurring_fault_code[inv.id]]
            out.append(Reading(
                ts=ts, inverter_id=inv.id, string_id=None,
                ac_power_w=round(inv_ac_w, 1),
                energy_kwh_cumulative=round(self._cum_energy[inv.id], 3),
                inverter_temp_c=round(env.ambient_temp_c + 12.0, 1),
                status_code=0 if inv.id not in f.outage_inverters else 3,
                fault_codes=fault_codes,
                riso_kohm=f.riso_kohm.get(inv.id),
                ground_fault=inv.id in f.ground_fault_inverters,
                arc_fault=inv.id in f.arc_fault_inverters,
            ))
        return out
