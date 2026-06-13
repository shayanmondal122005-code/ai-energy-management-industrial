# Safe deploy pipeline

Goal: **never let a broken change reach a hospital.** A change is checked, rolled
out slowly, and automatically cancelled if it misbehaves.

## How a change flows

```
you push / open PR
      │
      ▼
[1] CI gate  (.github/workflows/ci.yml)
      │   backend: ruff (real errors) + pytest
      │   frontend: lint + typecheck + build
      │   ── fails ──► merge blocked, nothing deploys
      ▼ passes, merged to main
[2] Railway builds the new backend, keeps the OLD one serving
      │   waits for /health/ready to pass  (healthcheckPath in railway.json)
      │   ── never healthy ──► traffic NEVER switches, deploy marked failed,
      │                        old version keeps running   ← auto-cancel
      ▼ healthy → traffic switches over (zero downtime)
[3] Verify deploy  (.github/workflows/verify-deploy.yml)
          polls production /health/ready for ~5 min
          ── stays unhealthy ──► auto-rollback to previous deploy + notify you
          ── healthy ──► done, deploy confirmed
```

Each requirement maps to one stage:

| You asked for | Stage |
|---|---|
| "first check if all good" | **[1]** CI gate — tests/lint/typecheck/build |
| "deployment slowly according to that" | **[2]** Railway healthcheck-gated rollout |
| "cancel updates if inconvenience happens" | **[2]** healthcheck never switches + **[3]** auto-rollback |

## The two health endpoints (important distinction)

- `GET /health` — **liveness**. Always returns 200. Keeps the container alive;
  Railway never kills it for a transient DB blip.
- `GET /health/ready` — **readiness / deploy gate**. Returns **503** when the
  database is unreachable. This is what Railway gates on. A new build that can't
  reach its DB (bad env var, broken migration, import crash) fails readiness, so
  its traffic switch never happens and the old version keeps serving.

DB is critical (gates deploys). Redis is best-effort, so a Redis hiccup does
*not* cause a false rollback.

## One-time setup

### 1. Branch protection (makes the CI gate real)
GitHub repo → Settings → Branches → Add rule for `main`:
- ✅ Require a pull request before merging
- ✅ Require status checks to pass → select **`Backend — lint + tests`** and **`Frontend — lint + typecheck + build`**

Now `main` can only receive code that passed CI, and Railway/Vercel deploy from `main`.

### 2. Railway healthcheck
Already wired in `railway.json` (`healthcheckPath: /health/ready`). Confirm in
Railway → service → Settings → Deploy that the health check path shows
`/health/ready`. Nothing else to do — Railway does the slow rollout natively.

### 3. Secrets (GitHub repo → Settings → Secrets → Actions)
For the frontend build to match prod:
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`

For the auto-rollback verifier (optional but recommended):
- `PROD_API_URL` — your production backend URL (e.g. `https://...up.railway.app`)
- `RAILWAY_API_TOKEN` — Railway account/project token
- `RAILWAY_SERVICE_ID` — backend service id (Railway → service → Settings)
- `RAILWAY_ENVIRONMENT_ID` — production environment id

If the Railway secrets are absent, the verifier still polls and fails loudly on a
bad deploy — it just prints manual rollback steps instead of doing it for you.

## Manual rollback (always available)
- **Backend (Railway):** dashboard → service → Deployments → pick the last good
  one → Rollback. Instant.
- **Frontend (Vercel):** dashboard → Deployments → previous → Promote to
  Production. Or `vercel rollback`.
- **Run the verifier on demand:** Actions → "Verify deploy" → Run workflow.

## Notes / future
- Railway's GraphQL rollback schema in `scripts/verify_deploy.py` should be
  confirmed against your project once (run the verifier manually and watch the
  log) — Railway occasionally revises the API.
- When you outgrow this: add a separate Railway **staging** environment and
  promote staging → production only after a smoke test. The current setup is the
  right amount of process for 0–5 customers.
```
