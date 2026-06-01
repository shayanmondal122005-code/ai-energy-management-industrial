# MicroGrid AI — Deploy Guide
## From zero to live in 30 minutes

---

## What you need to create (all free tier)

| Service | URL | What for |
|---|---|---|
| Supabase | supabase.com | PostgreSQL + Auth + Realtime |
| Railway | railway.app | Backend hosting (no sleep) |
| Upstash | upstash.com | Redis cache |
| Vercel | vercel.com | Frontend hosting |
| Twilio | console.twilio.com | WhatsApp alerts |
| Sentry | sentry.io | Error tracking |

---

## Step 1 — Supabase (5 min)

1. Go to **supabase.com** → New project
2. Name: `microgrid-ai` | Region: `Southeast Asia (Singapore)` | Password: save it
3. Wait for project to initialize (~2 min)
4. Go to **Settings → Database** → copy **Connection string (URI)** → replace `[YOUR-PASSWORD]`
5. Go to **Settings → API** → copy:
   - Project URL
   - `anon public` key
   - `service_role secret` key

6. Go to **SQL Editor** → run these files IN ORDER:
   ```
   infrastructure/supabase/migrations/001_initial.sql
   infrastructure/supabase/migrations/002_indexes.sql
   infrastructure/supabase/seed.sql
   ```

---

## Step 2 — Upstash Redis (2 min)

1. Go to **console.upstash.com** → Create Database
2. Name: `microgrid-cache` | Region: `AP-Southeast-1`
3. Copy the **Redis URL** (starts with `rediss://`)

---

## Step 3 — Railway Backend (5 min)

1. Go to **railway.app** → New Project → Deploy from GitHub repo
2. Select `ai-energy-management-industrial`
3. Add these environment variables:

```env
DATABASE_URL=postgresql+asyncpg://postgres:[password]@db.[ref].supabase.co:5432/postgres
SUPABASE_URL=https://[ref].supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
REDIS_URL=rediss://default:[password]@[endpoint].upstash.io:6379
JWT_SECRET=[run: python -c "import secrets; print(secrets.token_hex(32))"]
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=xxx
ENVIRONMENT=production
DEBUG=false
```

4. Set **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 2`
5. Set **Root Directory**: leave empty (railway.json handles it)
6. Deploy → copy your Railway URL (e.g. `https://microgrid-backend.railway.app`)
7. Test: open `https://your-url.railway.app/health` — should return `{"status":"ok"}`

---

## Step 4 — Vercel Frontend (5 min)

1. Go to **vercel.com** → New Project → Import from GitHub
2. Select `ai-energy-management-industrial`
3. Set **Root Directory**: `frontend`
4. Add environment variables:

```env
NEXT_PUBLIC_API_URL=https://your-railway-url.railway.app
NEXT_PUBLIC_SUPABASE_URL=https://[ref].supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

5. Deploy → your dashboard is live at `https://microgrid-ai.vercel.app`

---

## Step 5 — Create your first user

Run this against your Railway backend:

```bash
curl -X POST https://your-railway-url.railway.app/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@apollohospital.in","password":"changeme123"}'
```

Or add a user directly in Supabase → Table Editor → `users` table.

---

## Step 6 — Start the data feeder

```bash
# On your laptop
pip install requests pvlib numpy pandas
python feeder.py
```

The feeder sends real Kolkata weather + hospital load to your backend every 15 minutes.

---

## Verify everything works

| Check | Expected |
|---|---|
| `GET /health` | `{"status":"ok","db":true,"redis":true}` |
| `GET /facilities/` | Returns Apollo Hospital |
| Dashboard loads | Shows LIVE badge, real data |
| Feeder running | New readings every 15 min |
| WhatsApp alert | Fires when battery < 20% |

---

## Troubleshooting

**Backend won't start**: Check Railway logs → usually a missing env var  
**DB connection fails**: Make sure DATABASE_URL uses `postgresql+asyncpg://` not `postgres://`  
**No data on dashboard**: Run feeder.py or POST to `/facilities/{id}/ingest`  
**Redis errors**: Check Upstash URL starts with `rediss://` (with SSL)  
**Frontend blank page**: Check browser console → usually NEXT_PUBLIC_API_URL wrong  
