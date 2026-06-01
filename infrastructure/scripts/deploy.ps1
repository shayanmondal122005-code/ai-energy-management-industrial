# MicroGrid AI — One-command deployment script (Windows PowerShell)
# Run this once after creating Supabase + Railway + Vercel accounts
# Usage: .\infrastructure\scripts\deploy.ps1

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   MicroGrid AI — Deployment Script       ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── STEP 1: Collect credentials ──────────────────────────────
Write-Host "STEP 1: Enter your credentials" -ForegroundColor Yellow
Write-Host "(Get these from supabase.com, railway.app, upstash.com, twilio.com)"
Write-Host ""

$DB_URL         = Read-Host "Supabase DATABASE_URL (postgresql://...)"
$SUPA_URL       = Read-Host "Supabase URL (https://xxx.supabase.co)"
$SUPA_ANON      = Read-Host "Supabase Anon Key"
$SUPA_SERVICE   = Read-Host "Supabase Service Role Key"
$REDIS_URL      = Read-Host "Upstash Redis URL (rediss://...)"
$JWT_SECRET     = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 64 | ForEach-Object {[char]$_})
$TWILIO_SID     = Read-Host "Twilio Account SID (ACxxx) [Enter to skip]"
$TWILIO_TOKEN   = Read-Host "Twilio Auth Token [Enter to skip]"
$SENTRY_DSN     = Read-Host "Sentry DSN [Enter to skip]"
$RAILWAY_TOKEN  = Read-Host "Railway API Token (from railway.app/account)"
$VERCEL_TOKEN   = Read-Host "Vercel Token (from vercel.com/account/tokens)"

Write-Host ""
Write-Host "Generated JWT_SECRET: $JWT_SECRET" -ForegroundColor Green
Write-Host ""

# ── STEP 2: Write .env ───────────────────────────────────────
Write-Host "STEP 2: Writing .env file..." -ForegroundColor Yellow
@"
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=$DB_URL
SUPABASE_URL=$SUPA_URL
SUPABASE_ANON_KEY=$SUPA_ANON
SUPABASE_SERVICE_ROLE_KEY=$SUPA_SERVICE
REDIS_URL=$REDIS_URL
JWT_SECRET=$JWT_SECRET
TWILIO_ACCOUNT_SID=$TWILIO_SID
TWILIO_AUTH_TOKEN=$TWILIO_TOKEN
SENTRY_DSN=$SENTRY_DSN
"@ | Out-File -FilePath ".env" -Encoding utf8
Write-Host "  .env written" -ForegroundColor Green

# ── STEP 3: Run Supabase migrations ─────────────────────────
Write-Host ""
Write-Host "STEP 3: Running database migrations..." -ForegroundColor Yellow
Write-Host "  Open https://supabase.com/dashboard → your project → SQL Editor"
Write-Host "  Paste and run these files IN ORDER:"
Write-Host "    1. infrastructure/supabase/migrations/001_initial.sql"
Write-Host "    2. infrastructure/supabase/migrations/002_indexes.sql"
Write-Host "    3. infrastructure/supabase/seed.sql  (demo data)"
Write-Host ""
$migDone = Read-Host "Have you run the migrations? (y/n)"
if ($migDone -ne "y") {
    Write-Host "Run migrations first, then re-run this script." -ForegroundColor Red
    exit 1
}

# ── STEP 4: Deploy backend to Railway ───────────────────────
Write-Host ""
Write-Host "STEP 4: Deploying backend to Railway..." -ForegroundColor Yellow
if (Get-Command railway -ErrorAction SilentlyContinue) {
    $env:RAILWAY_TOKEN = $RAILWAY_TOKEN
    railway up --service microgrid-backend
    Write-Host "  Backend deployed to Railway" -ForegroundColor Green
} else {
    Write-Host "  Railway CLI not found. Installing..." -ForegroundColor Yellow
    npm install -g @railway/cli
    $env:RAILWAY_TOKEN = $RAILWAY_TOKEN
    railway login --token $RAILWAY_TOKEN
    railway up --service microgrid-backend
}

# ── STEP 5: Set Railway environment variables ────────────────
Write-Host ""
Write-Host "STEP 5: Setting Railway env vars..." -ForegroundColor Yellow
$vars = @{
    DATABASE_URL             = $DB_URL
    SUPABASE_URL             = $SUPA_URL
    SUPABASE_ANON_KEY        = $SUPA_ANON
    SUPABASE_SERVICE_ROLE_KEY= $SUPA_SERVICE
    REDIS_URL                = $REDIS_URL
    JWT_SECRET               = $JWT_SECRET
    TWILIO_ACCOUNT_SID       = $TWILIO_SID
    TWILIO_AUTH_TOKEN        = $TWILIO_TOKEN
    SENTRY_DSN               = $SENTRY_DSN
    ENVIRONMENT              = "production"
}
foreach ($kv in $vars.GetEnumerator()) {
    if ($kv.Value) {
        railway variables set "$($kv.Key)=$($kv.Value)" 2>$null
    }
}
Write-Host "  Environment variables set" -ForegroundColor Green

# ── STEP 6: Get backend URL ──────────────────────────────────
$BACKEND_URL = railway domain 2>$null
if (-not $BACKEND_URL) { $BACKEND_URL = Read-Host "Enter your Railway backend URL (https://...railway.app)" }
Write-Host "  Backend URL: $BACKEND_URL" -ForegroundColor Green

# ── STEP 7: Deploy frontend to Vercel ───────────────────────
Write-Host ""
Write-Host "STEP 7: Deploying frontend to Vercel..." -ForegroundColor Yellow
Set-Location frontend
if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
    npm install -g vercel
}
$env:VERCEL_TOKEN = $VERCEL_TOKEN
vercel env add NEXT_PUBLIC_API_URL production <<< $BACKEND_URL
vercel env add NEXT_PUBLIC_SUPABASE_URL production <<< $SUPA_URL
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production <<< $SUPA_ANON
vercel --prod --token $VERCEL_TOKEN
Set-Location ..

# ── Done ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   MicroGrid AI is LIVE                   ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Backend : $BACKEND_URL" -ForegroundColor Cyan
Write-Host "  API Docs: $BACKEND_URL/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next: run feeder.py to start sending live data" -ForegroundColor Yellow
