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
