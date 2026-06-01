# MicroGrid AI — Architecture

## System Overview

12-layer production architecture. Each layer is independent and replaceable.

```
Browser / Mobile
      │
      ▼
┌─────────────────────────────────┐
│   Next.js 14 (Vercel)           │  Layer 1 — Frontend
│   TypeScript + Tailwind + shadcn│
│   Recharts + react-flow         │
└──────────────┬──────────────────┘
               │ HTTPS + JWT
               ▼
┌─────────────────────────────────┐
│   FastAPI (Railway)             │  Layer 2 — Backend API
│   Clean layered architecture    │
│   api/ → services/ → repos/     │
└──────┬──────────────┬───────────┘
       │              │
       ▼              ▼
┌──────────┐   ┌──────────────────┐
│  Redis   │   │  PostgreSQL 15   │  Layers 3 + 6
│ (Upstash)│   │  (Supabase)      │
└──────────┘   └──────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Supabase        │  Layer 5 — Real-time
              │ Realtime        │  (WebSocket to frontend)
              └─────────────────┘
```

## Build Phases

### Phase 1 — Foundation (CURRENT)
- [x] Repository structure
- [x] Supabase schema + RLS policies
- [x] Backend core (config, DB, security, cache)
- [x] Layered architecture scaffold
- [x] GitHub Actions CI/CD
- [ ] Connect backend to real Supabase DB
- [ ] Migrate all existing service logic into services/

### Phase 2 — Backend complete
- [ ] All API endpoints working against PostgreSQL
- [ ] Redis caching on all expensive operations
- [ ] APScheduler background jobs running
- [ ] Rate limiting on all endpoints
- [ ] Sentry error tracking

### Phase 3 — Frontend
- [ ] Next.js setup + all pages
- [ ] Real-time via Supabase channels
- [ ] Mobile responsive

### Phase 4 — Production hardening
- [ ] Load testing (5 concurrent facilities)
- [ ] Backup + restore tested
- [ ] RUNBOOK.md written

### Phase 5 — Customer ready
- [ ] Onboarding flow
- [ ] Demo facility (Apollo Hospital data)
- [ ] Weekly PDF reports
- [ ] WhatsApp alerts end-to-end

## Security model

- JWT tokens, 1hr expiry, refresh rotation
- Row Level Security on every Postgres table
- 5 roles: super_admin, tenant_admin, operator, viewer, api_key
- Control commands: 2-step confirm + 60s expiry
- P1 loads blocked in code (not just policy)
- Audit log is append-only — no user can delete rows

## Upgrade path

Current (0-5 customers):
  Backend → Railway ($5/month, always-on)
  DB → Supabase free tier (500MB)
  Cache → Upstash free tier

10+ customers:
  Backend → AWS EC2 t3.medium, Mumbai region (~$30/month)
  DB → RDS PostgreSQL Multi-AZ
  Cache → ElastiCache Redis
  CDN → CloudFront
