# MicroGrid AI — Industrial Edition
## Context for AI sessions

### What this is
Production-grade India-native energy management SaaS.
Builder: Shayan Mondal (shayanmondal122005@gmail.com), physics student, Kolkata.
Stage: Acquiring first 3 paying customers. Not a prototype — real product.

### Live URLs (original prototype — still running)
- Dashboard: https://ai-energy-management.streamlit.app
- Backend: https://ai-energy-managementat12.onrender.com

### This repo (production rebuild)
- GitHub: https://github.com/shayanmondal122005-code/ai-energy-management-industrial

### Architecture
See docs/ARCHITECTURE.md for full system design.

- **Frontend**: Next.js 14 + TypeScript + Tailwind + shadcn → Vercel
- **Backend**: FastAPI (Python 3.11) → Railway
- **Database**: PostgreSQL 15 on Supabase (+ Auth + Realtime + Storage)
- **Cache**: Redis on Upstash
- **CI/CD**: GitHub Actions

### Existing physics — DO NOT change
All existing AI and physics logic is correct and must be preserved:
- XGBoost 24h load forecasting (backend/services/forecasting.py)
- Coulomb counting + Arrhenius battery SoC (backend/services/battery_tracker.py)
- IEC 61850 three-layer grid switching (backend/services/grid_controller.py)
- Solar health 4 detectors (backend/services/solar_health.py)
- India tariff engine — 5 states in frontend/types/index.ts

### Build phase
Currently in Phase 1 (Foundation). See docs/ARCHITECTURE.md for full plan.
Next step: Phase 2 — complete all API endpoints and connect to real Supabase DB.

### Engineering standards (non-negotiable)
- TypeScript strict mode — no `any` types
- Pydantic validation on every API input
- P1 loads (ICU, OT, life support) can NEVER be shed — blocked in code
- Grid switch commands require 2-step confirmation
- All control actions go to audit_log
- No hardcoded secrets — all from environment variables

### Key files
- infrastructure/supabase/migrations/001_initial.sql — full DB schema + RLS
- backend/core/config.py — all settings from env vars
- backend/core/security.py — JWT + role system
- backend/api/v1/grid.py — grid control with safety interlocks
- frontend/types/index.ts — TypeScript types + India tariff constants

---

## Build log — KEEP THIS UPDATED EACH SESSION (per Shayan's instruction)
Register every meaningful change here so this file stays the running record.

### Workflow now in force
- `main` is BRANCH-PROTECTED: every change goes via PR; CI checks "Backend — lint + tests"
  and "Frontend — lint + typecheck + build" must pass before merge. No direct pushes.
- Safe deploy: Railway healthcheck on `/health/ready` (strict, 503 on DB down) gates rollout;
  `verify-deploy` workflow + `scripts/verify_deploy.py` poll prod after deploy and auto-roll-back.

### 2026-06-13 — session (PRs #2–#10, all merged green)
- **#2 Safe deploy pipeline**: `.github/workflows/ci.yml`, `verify-deploy.yml`, `scripts/verify_deploy.py`,
  `pyproject.toml` (ruff+pytest), strict `/health/ready` in `backend/main.py`, `railway.json` healthcheck,
  `docs/CICD.md`. Branch protection enabled.
- **#3** verify_deploy skips gracefully when `PROD_API_URL` unset.
- **#4 Optimizer fixes** (`optimizer_v2.py`): degradation was double-counted (charge+discharge) → now
  discharge-only (Rs1.67/kWh-discharged); added terminal-SoC floor (end ≥ start) so it can't fake savings by
  draining. Un-xfail'd 3 tests; `test_temperature_reduces_capacity` corrected to match the locked capacity model.
- **#5 Shadow-savings**: `services/shadow_savings.py` + `GET /facilities/{id}/savings/shadow` +
  `readings_repo.get_hourly_for_shadow` — replays REAL load history through the optimizer for defensible savings.
  `docs/AUDIT-2026-06-13.md`.
- **#6 Savings page**: shows MEASURED shadow-savings; projection kept only as labeled fallback.
- **#7 Edge demo (meter-less loop)**: `edge/feeder/laptop_feeder.py` (laptop = meter, closed loop, verified
  live), `edge/arduino/esp32_led_output.ino` (LED = relay: solid=charge, blink=discharge), `esp32_meter_bringup.ino`.
- **#8** LED firmware: slow heartbeat when cloud link stale (never freezes on old command).
- LED firmware DEVICE_KEY pre-filled with the sim-hospital-01 demo key (matches laptop_feeder.py) so the
  demo flashes with only WiFi to edit. Key verified live (HTTP 200). Rotate before any real pilot.
- **#9 Telemetry→readings bridge** (`sim.py` + `services/telemetry_bridge.py`): mirrors device telemetry into
  `readings` when `facilities.site_id` matches device site. SAVEPOINT-isolated; no-op until mapped. Needs
  `backend/migrations/2026_06_add_facility_site_id.sql` run on Supabase + `docs/PILOT-ONBOARDING.md`.
- **#10 PF/kVA engine** (`services/pf_penalty.py` + `pf_threshold`/`pf_penalty_pct` in INDIA_TARIFFS): industrial
  power-factor penalty + kVA-demand calc. Usable for bill audit now; goes live once PF is stored (readings/telemetry
  don't carry PF yet — follow-up).

### 2026-06-20 — edge demo session
- ESP32 LED firmware (`esp32_led_output.ino`) reworked into a 6-LED relay panel (one LED per relay command:
  GPIO 25 GRID, 26 SOLAR, 27 BATT, 14 DG, 33 CHARGE, 32 DISCHARGE; onboard GPIO2 = link status) and made
  LIBRARY-FREE (jsonBool parser, no ArduinoJson). NOTE: the on-machine copy holds Shayan's WiFi creds and is
  intentionally UNCOMMITTED (password kept out of git) — repo copy still single-LED + needs a placeholder-creds sync.
- `laptop_feeder.py`: SoC banded to 20-90% (was clamping to 100%). Shayan correctly flagged 100% hold harms battery
  life; real optimizer already caps 15-95% + degradation penalty, so 100% was only the toy feeder overshooting.
- Reminder: ESP32 is 2.4GHz only; demo needs internet on both laptop + ESP32 (brain is cloud-side).

### 2026-06-20 — PF advisory module
- `backend/services/pf_advisor.py` (+ `test_pf_advisor.py`, 9 tests): the EMS's PF *intelligence* layer.
  PF is corrected by HARDWARE (capacitor bank — DISCOM-mandated — or 4-quadrant inverter); software doesn't
  correct PF itself. Module: `capacitor_kvar_required` (size the bank), `kvah_pf_premium_rs` (cost on kVAh-billed
  tariffs like Jharkhand), `pf_health` (monitor/alert when correction degrades), `pf_advice` (top-level).
  Reactive INVERTER control is GATED behind `reactive_capable=False` (default) — NEVER emits a command without a
  confirmed 4-quadrant inverter; otherwise returns control_mode="advisory" (recommend + monitor a capacitor bank).
- Tariff insight (verified from JSERC JBVNL FY2026-27 order): Jharkhand HT = flat Rs6.40/kVAh + Rs400/kVA, NO ToD,
  Load Factor Rebate <=15%. So battery ARBITRAGE earns ~0 in Jharkhand; EMS value = demand shaving + the
  load-factor rebate that peak-flattening unlocks (~Rs1.3L); PF/kVAh (~Rs2.1L) is the mandated capacitor bank.

### Hardware / electrician deliverables (generators live in the `prj` working folder, not this repo)
- `MicroGrid_wiring_sheets.pdf` — sheet 1 grid meter (electrician), sheet 2 control panel (EPC).
- `MicroGrid_solar_meter_sheet.pdf` — solar generation meter on PV inverter output (only if inverter unreadable).
- ESP32↔MFM384: 5V→VCC, GND→GND, GPIO17→DI, GPIO16→RO, GPIO4→DE+RE; A/B→meter; 120Ω; 9600 8N1 slave id 1.
- Multiple meters share ONE RS485 bus (grid=ID 1, solar=ID 2). Often only 1 meter needed + read the inverter.

### 2026-06-29 — solar management features (making solar first-class)
- **Soiling → cleaning-ROI recommender** (`backend/services/solar_cleaning_roi.py` + `test_solar_cleaning_roi.py`,
  12 tests): turns the solar-health Performance Ratio into a rupee wash decision. `soiling_loss_fraction`
  (gap below a clean array's PR ~0.95 = the soiling-attributable loss), `daily_kwh_lost` (anchored on the kWh the
  array ACTUALLY made today, not nameplate), `cleaning_advice` → "clean_now | monitor | clean_not_needed" with
  ₹/day lost, ₹ accrued since last wash, and payback days. HONEST: it FINDS the loss + RECOMMENDS; it does not
  "deliver" recovered energy. Solar valued at the NORMAL self-consumption rate (never peak — no overclaim).
  Endpoint `GET /facilities/{id}/solar/cleaning-roi?cleaning_cost_rs=&days_since_clean=` in `api/v1/alerts.py`
  (reuses run_solar_health PR + get_solar_generation today_kwh + facility.state_tariff normal rate).

- **Solar ROI / payback tracker** (`backend/services/solar_roi.py` + `test_solar_roi.py`, 9 tests): rolls lifetime
  solar kWh into the investor view — `value_to_date_rs`, `recovered_pct` (capped 100), `remaining_rs`, lifetime CO₂ +
  trees-equivalent, and a straight-line `payback_eta_days/years` from the recent run rate. Value = self-consumed kWh
  at the NORMAL grid rate (measured generation only; no sunnier-future assumption). Also lifted the previously
  UNTESTED `get_solar_generation` energy math into a pure `energy_kwh(avg_kw, min_ts, max_ts)` helper (now unit-tested)
  and wired `readings_repo` to use it. Endpoint `GET /facilities/{id}/solar/payback?system_cost_rs=` in `readings.py`
  (run rate = month_kwh / day-of-month). NOTE: the raw SQL in get_solar_generation is Postgres-only (FILTER/date_trunc),
  so it is still integration-tested against prod, not in CI — but its kWh math is now covered.

- **Optimizer solar curtailment/export** (`backend/services/optimizer_v2.py` + 6 new tests): added a per-hour solar
  SPILL variable to the LP power balance (`load = solar + grid + discharge − charge − spill`), so a high-solar day can
  NEVER be infeasible (the known bug: surplus solar had nowhere to go once the battery filled). Spill is bounded by
  that hour's solar. By DEFAULT spill is CURTAILED (wasted, 0 value) → `solar_curtailed_kwh`; only when
  `export_allowed=True` AND `export_rate>0` is it credited as `solar_exported_kwh` + `export_value_rs` (subtracted from
  cost_total) — same capability-gating as pf_advisor, because most India C&I has no/zero feed-in. The LP still prefers
  self-consumption + storage over spilling when there's an economic reason to store. New fields also surfaced in the
  `GET /facilities/{id}/optimize` response. Existing optimizer tests unaffected (their scenarios are solar-poor → spill=0).

- **Irradiance-based solar forecast** (`backend/services/solar_forecast.py` + `test_solar_forecast.py`, 13 tests):
  replaces the clear-sky sine curve feeding the optimizer with a forecast driven by REAL predicted GHI from Open-Meteo
  (`shortwave_radiation` + `temperature_2m`). STC-referenced yield model (no PVLib dep): `T_cell` via NOCT,
  `P_ac = kWp·(GHI/1000)·(1−system_loss)·[1+γ(T_cell−25)]` clipped to nameplate. Pure conversion funcs unit-tested;
  `fetch_open_meteo_ghi` isolates the I/O. Wired into `optimize.py` via `_solar_forecast_with_irradiance(facility,...)`
  using facility.lat/lon/solar_kw/timezone, with graceful FALLBACK to the old sine curve on any failure. Verified live
  (Kolkata): tracks monsoon cloud dips the sine curve couldn't. HONEST scope: uses horizontal GHI, not a full
  tilt/azimuth plane-of-array transposition — that (and per-facility tilt/azimuth/system-loss config) is the next refinement.

### 2026-06-30 — Solar O&M detection integration (merge of the solar-om-detection repo)
- Vendored the **pure detection core** from the standalone `solar-om-detection` repo into
  `backend/services/solar_om/` (framework-free by design — models, baseline PR/PR_tcorr engine,
  environmental gate, 7 detectors + meter/inverter cross-check, satellite/forecast sources, engine,
  seed). 88 vendored unit tests in `backend/tests/solar_om/` (pure, network-free) — green.
- `backend/services/solar_om_adapter.py` + `GET /facilities/{id}/solar/om-detection` (in `alerts.py`):
  runs the detection core on the EMS's PLANT-LEVEL solar readings — attaches modeled irradiance
  (Open-Meteo, low-latency; NASA POWER lags days so it's for backtests) + forecast SERVER-SIDE, runs
  detection through the gate, returns ₹-quantified / risk-framed alerts + health for the dashboard.
  Per-string + safety detectors stay dormant until an inverter gateway feeds per-string telemetry.
- **Calibration from history** (`solar_om/history.calibrate_from_hourly` + adapter `_calibration`):
  fits `eta_bos` + `baseline_pr` from the facility's OWN clean clear-sky history (21-day hourly solar
  vs modeled POA), cached 24h. Falls back to the 0.80 default until enough clear days accumulate; the
  dashboard's "uncalibrated estimate" chip clears once it's fit. Response now carries `eta_bos`/
  `baseline_pr`. (Slope/zero-power detectors never needed it; absolute-shortfall ones use ≥15%.)
  TODO: wire `EmsForecastAdapter` to the in-house forecast.
- **Dashboard panel** (`frontend/app/(dashboard)/solar/page.tsx` + `lib/api.ts` `solarOmDetection`):
  "Remote O&M Detection" section on the solar page — ₹/day at risk, open findings + suppressed count,
  sky/cloud-variability, and ₹-quantified / risk-framed alert cards. So all detection output lands in
  the one EMS dashboard. typecheck + lint clean.
- Source of truth for the detection logic stays the `solar-om-detection` repo; this is a vendored copy.

### Open follow-ups
- Store PF from the meter (firmware read + a `pf` column) so PF penalty runs on live data.
- Weekly PDF report (still a stub: `tasks.py:384`, `reports.py`).
- `month_peak_so_far_kw=0.0` hardcoded in `optimize.py` (demand charge slightly optimistic).
- `source_configs` table (mirror `load_configs`) so SOURCES are per-facility configurable like loads.
- Rotate the device key committed in `edge/wokwi/prakriti_esp32.ino` before any real pilot.
- Prune ~9 duplicate Vercel projects; pick one frontend host (Vercel vs Netlify).
- Per-facility solar config (kWp/tilt/azimuth/system_loss/panel_type) → full plane-of-array transposition in
  `solar_forecast.py` (currently uses horizontal GHI + defaults). Same table could feed solar_cap into solar_health.
- Frontend: surface the new solar endpoints — `/solar/cleaning-roi`, `/solar/payback`, and optimizer curtailment/
  export accounting — on `solar/page.tsx` + `savings/page.tsx` (backends shipped, UI not yet wired).
