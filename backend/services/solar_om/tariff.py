"""DISCOM tariff → ₹/kWh. Slab structure mirrors the EMS tariff engine (ToD-aware)
so every generation-loss alert ends in a rupee/day number.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Tariff:
    """Time-of-day energy tariff. `slabs` is hour→₹/kWh; `default` covers any gap.

    Solar offsets the rate the site would otherwise PAY the grid (self-consumption),
    so we value lost generation at the consumption tariff, not a feed-in rate —
    consistent with India C&I where export is usually nil/uneconomic.
    """
    id: str
    name: str
    default_rate: float
    slabs: dict[int, float]  # hour-of-day (0-23) → ₹/kWh

    def rupee_per_kwh(self, ts: datetime) -> float:
        return self.slabs.get(ts.hour, self.default_rate)

    @classmethod
    def flat(cls, rate: float, id: str = "flat", name: str = "Flat") -> "Tariff":
        return cls(id=id, name=name, default_rate=rate, slabs={})

    @classmethod
    def from_tod(cls, *, cheap: float, normal: float, peak: float,
                 cheap_hours: range, peak_hours: range,
                 id: str = "tod", name: str = "ToD") -> "Tariff":
        slabs: dict[int, float] = {}
        for h in range(24):
            if h in cheap_hours:
                slabs[h] = cheap
            elif h in peak_hours:
                slabs[h] = peak
            else:
                slabs[h] = normal
        return cls(id=id, name=name, default_rate=normal, slabs=slabs)
