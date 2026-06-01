# MicroGrid AI — Industrial Edition

> Production-grade India-native energy management platform for hospitals, campuses, and industrial facilities.

[![Tests](https://github.com/shayanmondal122005-code/ai-energy-management-industrial/actions/workflows/test.yml/badge.svg)](https://github.com/shayanmondal122005-code/ai-energy-management-industrial/actions)

---

## What this is

AI-powered energy management SaaS built for India's mid-market — 100–500 bed hospitals, university campuses, factories. Modelled on AutoGrid ($200M acquisition) and Arcadia ($200M raised) but India-native.

**Pricing:** ₹40,000–80,000/month per facility  
**USP:** India DISCOM tariffs, monsoon solar model, WhatsApp-first, 48hr deployment

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 + TypeScript + Tailwind + shadcn/ui |
| Backend | FastAPI (Python 3.11) |
| Database | PostgreSQL 15 on Supabase |
| Cache | Redis on Upstash |
| Real-time | Supabase Realtime (WebSocket) |
| AI/ML | XGBoost 24h load forecasting |
| Physics | Coulomb counting + Arrhenius battery model |
| Grid | IEC 61850 three-layer architecture |
| Hosting | Railway (backend) + Vercel (frontend) |
| CI/CD | GitHub Actions |

---

## Features

- **AI Load Forecasting** — XGBoost 24h ahead, < 8% MAPE, confidence bands
- **Physics Battery Model** — Coulomb counting + Arrhenius temperature correction + cycle degradation
- **Brain Decision Engine** — 6 rules: emergency charge, ToD arbitrage, demand shave, pre-charge
- **India Tariff Engine** — 5 states: CESC, MSEDCL, TANGEDCO, BESCOM, BSES/TPDDL
- **Grid Controller** — IEC 61850, modes: GRID_CONNECTED/ISLAND/TRANSITION/EMERGENCY, 2-step confirm
- **Load Priority Ladder** — P1-P5, 24 loads, P1 (ICU/OT/life support) blocked in code
- **Solar Health** — 4 detectors: soiling, sudden drop, degradation trend, storm warning
- **WhatsApp Alerts** — Twilio, critical alerts in < 60 seconds
- **Multi-tenant** — Row Level Security, 5 roles, full audit log

---

## Deploy in 30 minutes

See **[docs/DEPLOY.md](docs/DEPLOY.md)** — step-by-step from zero to live.

Local dev (Docker):
```bash
docker compose up
```

---

## Structure

```
backend/          FastAPI (api/ services/ repositories/ models/ core/ jobs/)
frontend/         Next.js 14 (10 pages: dashboard, forecast, grid, battery, solar, savings, alerts...)
infrastructure/   Supabase SQL migrations + seed data
.github/          CI/CD workflows
docs/             ARCHITECTURE.md + DEPLOY.md
```

---

Built by Shayan Mondal — Physics student, Kolkata · shayanmondal122005@gmail.com
