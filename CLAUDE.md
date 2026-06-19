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
- **#9 Telemetry→readings bridge** (`sim.py` + `services/telemetry_bridge.py`): mirrors device telemetry into
  `readings` when `facilities.site_id` matches device site. SAVEPOINT-isolated; no-op until mapped. Needs
  `backend/migrations/2026_06_add_facility_site_id.sql` run on Supabase + `docs/PILOT-ONBOARDING.md`.
- **#10 PF/kVA engine** (`services/pf_penalty.py` + `pf_threshold`/`pf_penalty_pct` in INDIA_TARIFFS): industrial
  power-factor penalty + kVA-demand calc. Usable for bill audit now; goes live once PF is stored (readings/telemetry
  don't carry PF yet — follow-up).

### Hardware / electrician deliverables (generators live in the `prj` working folder, not this repo)
- `MicroGrid_wiring_sheets.pdf` — sheet 1 grid meter (electrician), sheet 2 control panel (EPC).
- `MicroGrid_solar_meter_sheet.pdf` — solar generation meter on PV inverter output (only if inverter unreadable).
- ESP32↔MFM384: 5V→VCC, GND→GND, GPIO17→DI, GPIO16→RO, GPIO4→DE+RE; A/B→meter; 120Ω; 9600 8N1 slave id 1.
- Multiple meters share ONE RS485 bus (grid=ID 1, solar=ID 2). Often only 1 meter needed + read the inverter.

### Open follow-ups
- Store PF from the meter (firmware read + a `pf` column) so PF penalty runs on live data.
- Weekly PDF report (still a stub: `tasks.py:384`, `reports.py`).
- `month_peak_so_far_kw=0.0` hardcoded in `optimize.py` (demand charge slightly optimistic).
- `source_configs` table (mirror `load_configs`) so SOURCES are per-facility configurable like loads.
- Rotate the device key committed in `edge/wokwi/prakriti_esp32.ino` before any real pilot.
- Prune ~9 duplicate Vercel projects; pick one frontend host (Vercel vs Netlify).
