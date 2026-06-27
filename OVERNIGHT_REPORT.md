# Overnight Report — Cost-Optimizer Benchmark (2026-06-20)

Branch: `overnight/cost-optimizer-20260620` — **did NOT touch main, did NOT open a PR.**

## TL;DR
- **Target:** reduce the monthly hospital bill by ≥ **₹1,50,000**.
- **Result: ₹1,97,645/month saved → TARGET MET.** Safety violations: **0**. Optimizer status: `optimal`.
- ⚠️ **Read the honest caveat below before quoting ₹1.97L to anyone** — the savings are dominated by power-factor correction, not the battery.

## Numbers (`benchmark_result.json`)
| | ₹/month |
|---|---|
| Baseline (no EMS) | 18,36,299 |
| Optimized (with EMS) | 16,38,654 |
| **Savings** | **1,97,645** |

**Lever breakdown:**
| Lever | ₹/month |
|---|---|
| Power-factor correction | **1,66,936** |
| Peak-demand shaving | 24,192 |
| ToD energy arbitrage | 19,446 |
| Battery wear (cost) | −12,930 |

## ⚠️ Honest caveat — REVIEW THIS FIRST
- ₹1.5L is achievable, but **PF correction is ~85% of the savings** — *not* the battery.
- **Battery dispatch alone** (arbitrage + demand shave − wear) ≈ **₹30.7k/month.** That's the honest "what the battery scheduling delivers" number.
- The ₹1.67L PF figure assumes PF is corrected 0.85 → 0.96. That requires the **battery inverter to provide reactive support, OR a capacitor bank (APFC panel)**. If it's a capacitor bank, that's a separate (cheap) investment — the EMS's role is to **detect, quantify, and recommend** it. Do not present the PF saving as "battery savings."
- `pf_threshold`/`pf_penalty_pct` are approximate CESC defaults — confirm against the customer's actual tariff order.

→ For a customer, lead with **PF + demand charge** (matches your meeting prep); the battery is the smaller, supporting lever.

## Assumptions (`benchmark_config.json`)
500 kW peak · 280,000 kWh/month · 250 kWp solar (~1,100 kWh/day) · 500 kWh / 250 kW battery · RTE 0.90 · SoC band 20–90% · sanctioned 600 kVA · PF 0.85→0.96 · tariff West Bengal CESC (cheap 4.20 / normal 6.10 / peak 7.85, demand ₹320/kW, PF penalty 1%/0.01 below 0.95). Representative-day simulation scaled ×30; demand billed on that day's peak.

## Algorithm
Built **on the existing `optimize_dispatch_v2`** — a Linear Program (scipy HiGHS) minimizing energy + demand + battery-wear cost, subject to power balance, SoC band, inverter rating, terminal-SoC, and a **new sanctioned grid-import cap**. PF is computed separately via `pf_penalty.py` (it isn't a dispatch variable). No heuristic/MILP rebuild was needed — the LP already hit the target; further dispatch tuning shows **diminishing returns vs the PF lever**, so per the loop's stop rule, iteration stopped.

## Safety (enforced in code + tested)
- **Recommendation-only:** returns a setpoint schedule; never emits an IEC 61850 / control command (documented in the docstring; actuation is a separate gated layer).
- **Fail-safe validation:** bad/missing input → `_safe_noop` (all zeros, status `invalid_input`), never an undefined/unsafe state.
- **Physical limits:** SoC floor/ceiling (20/90), inverter C-rate (max charge/discharge kW), sanctioned grid-import cap (`max_grid_kw`). Benchmark verified **0 violations**.
- New: `backend/tests/test_optimizer_safety.py` (7 tests, pass locally).

## Security audit
- **Secrets: clean** — no hardcoded secrets in `backend/*.py`. (Known device key is in `edge/wokwi/prakriti_esp32.ino` — separately flagged; rotate before pilot.)
- **Dependency CVEs (pip-audit):** ran against the local env (mixed with tooling). **Backend-relevant:** `requests` (CVE-2024-47081 → fix 2.32.4) and `urllib3` (several → fix ≥2.5.0). `tornado`/`werkzeug`/`flask` are **not** backend deps. `requirements.txt` uses flexible ranges, so prod already pulls patched versions. **Recommend** pinning `requests>=2.32.4`, `urllib3>=2.5.0`; **no major upgrades. Not auto-applied.**
- **Multi-tenant isolation:** `/optimize` enforces `current_user.can_access_facility()`. Added `backend/tests/test_tenant_isolation.py` proving tenant A cannot read tenant B's facility.
- **AuthN/AuthZ:** `/optimize` already requires JWT and enforces tenant scope.
- **Audit log:** added `AUDIT optimize_recommendation facility=… tenant=… status=… savings=… ts=…` on every recommendation (a full DB `audit_log` row is a follow-up).

## Could NOT fully verify (be aware)
- **FastAPI/bcrypt-dependent tests didn't run in this overnight env** (bcrypt not installed). They compile and will run in CI. **Before merging, open a PR so CI runs the full suite.** 39 pure-Python tests DO pass here.
- Single representative day ×30 + flat PF — fine for a benchmark, not a substitute for real metered data.

## Review first in the morning
1. The **honest framing** (dispatch ≈ ₹31k, PF ≈ ₹1.67L) — decide how you present it.
2. `benchmark_result.json` — full numbers/breakdown/assumptions.
3. `max_grid_kw` cap + `_safe_noop` in `optimizer_v2.py` — confirm they match your intent.
4. **Open a PR** so CI runs the FastAPI tests (I did not — guardrail).
5. Whether to wire PF into the live `/savings/shadow` (currently benchmark-only; needs PF stored from the meter).

## Workflow
Branch `overnight/cost-optimizer-20260620`; no main commits, no PR; pushed to origin. Logical commits, runnable tests green before each.
