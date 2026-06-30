"""Shared detector helpers + the idempotent AlertStore.

Detectors are pure: they consume domain data + baseline outputs and return
AlertDraft objects. The AlertStore reconciles drafts against currently-open alerts
so re-running a detector updates (not duplicates) an alert, and a cleared condition
closes it. An in-memory store backs the tests; a SQLModel-backed store (app/db)
implements the same interface for production.
"""
from __future__ import annotations

from datetime import datetime

from backend.services.solar_om.models import AlertDraft, AlertStatus, Severity


def rupee_per_day(loss_fraction: float, expected_kwh_day: float, tariff_rate: float) -> float:
    """₹/day lost = loss_fraction × expected daily energy × ₹/kWh."""
    return round(max(0.0, loss_fraction) * max(0.0, expected_kwh_day) * max(0.0, tariff_rate), 2)


class InMemoryAlertStore:
    """Reconciles AlertDrafts → open alerts. Keyed by AlertDraft.dedup_key so a
    detector is idempotent: same condition updates the same row; a missing draft
    for a previously-open alert closes it."""

    def __init__(self):
        self._open: dict[tuple, dict] = {}
        self._closed: list[dict] = []
        self._suppressed: list[dict] = []
        self._seq = 0

    def _row(self, draft: AlertDraft, ts: datetime) -> dict:
        self._seq += 1
        return {
            "id": self._seq, "opened_at": ts, "closed_at": None,
            **{k: getattr(draft, k) for k in (
                "plant_id", "inverter_id", "string_id", "type", "severity",
                "recommended_action", "confidence", "rupee_impact_per_day",
                "rupee_accumulated", "risk_note", "evidence")},
            "status": draft.status,
        }

    def record_suppressed(self, draft: AlertDraft, ts: datetime, reason: str) -> None:
        """Gate-suppressed deviations are logged for AUDIT, not shown as faults."""
        row = self._row(draft, ts)
        row["status"] = AlertStatus.SUPPRESSED
        row["evidence"] = {**(draft.evidence or {}), "suppressed_reason": reason}
        self._suppressed.append(row)

    def reconcile(self, drafts: list[AlertDraft], ts: datetime, *,
                  scope_types: set[str] | None = None) -> None:
        """Open/update alerts for the given drafts. If scope_types is given, any
        currently-open alert of those types WITHOUT a matching draft is closed
        (the condition cleared)."""
        seen = set()
        for d in drafts:
            key = d.dedup_key
            seen.add(key)
            if key in self._open:
                row = self._open[key]
                for f in ("severity", "confidence", "rupee_impact_per_day",
                          "rupee_accumulated", "risk_note", "recommended_action", "evidence"):
                    row[f] = getattr(d, f)
                row["status"] = d.status
            else:
                self._open[key] = self._row(d, ts)

        if scope_types:
            for key, row in list(self._open.items()):
                if row["type"] in scope_types and key not in seen:
                    self.close(key, ts, reason="condition cleared")

    def move_to_verifying(self, key: tuple, ts: datetime) -> bool:
        if key in self._open:
            self._open[key]["status"] = AlertStatus.VERIFYING
            self._open[key]["verifying_since"] = ts
            return True
        return False

    def close(self, key: tuple, ts: datetime, *, reason: str = "",
              recovery: dict | None = None) -> dict | None:
        row = self._open.pop(key, None)
        if row is None:
            return None
        row["status"] = AlertStatus.RESOLVED
        row["closed_at"] = ts
        row["close_reason"] = reason
        if recovery:
            row["recovery"] = recovery
        self._closed.append(row)
        return row

    # ── queries (used by API/health + tests) ─────────────────────────────────
    def open_alerts(self) -> list[dict]:
        return list(self._open.values())

    def open_by_type(self, type_: str) -> list[dict]:
        return [r for r in self._open.values() if r["type"] == type_]

    def suppressed(self) -> list[dict]:
        return list(self._suppressed)

    def closed(self) -> list[dict]:
        return list(self._closed)

    def find_open(self, plant_id: str, type_: str, *, inverter_id=None, string_id=None):
        return self._open.get((plant_id, inverter_id, string_id, type_))


SEVERITY_ORDER = {Severity.INFO: 0, Severity.INVESTIGATE: 1, Severity.CRITICAL: 2}
