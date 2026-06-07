"""MicroGrid AI — FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.api.v1 import auth, facilities, readings, grid, alerts, reports, forecast, optimize, safety, sim
from backend.core.cache import ping_redis
from backend.core.config import get_settings
from backend.core.database import ping_db
from backend.core.rate_limit import limiter
from backend.jobs.scheduler import start_scheduler, stop_scheduler

settings = get_settings()
logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        environment=settings.environment,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MicroGrid AI v%s starting — env=%s", settings.app_version, settings.environment)
    try:
        await start_scheduler()
    except Exception as e:
        logger.warning("Scheduler failed to start: %s — continuing without it", e)
    yield
    try:
        await stop_scheduler()
    except Exception:
        pass
    logger.info("MicroGrid AI shutting down")


app = FastAPI(
    title="MicroGrid AI API",
    version=settings.app_version,
    description="Production-grade India-native energy management platform",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_origins = [
    "https://microgrid-ai.vercel.app",
    "https://gleeful-elf-259dad.netlify.app",
    "http://localhost:3000",
]
if settings.debug:
    _origins.append("http://localhost:3001")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Allow any Netlify/Vercel preview/prod domain + localhost so the dashboard
    # (Prakriti Energy front-end) can call the API from any deploy URL.
    allow_origin_regex=r"https://([a-z0-9-]+\.)*(netlify|vercel)\.app|http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - start) * 1000
    logger.info("method=%s path=%s status=%d latency_ms=%.1f",
                request.method, request.url.path, response.status_code, latency_ms)
    return response


app.include_router(auth.router,       prefix="/auth",       tags=["auth"])
app.include_router(facilities.router, prefix="/facilities", tags=["facilities"])
app.include_router(readings.router,   prefix="/facilities", tags=["readings"])
app.include_router(grid.router,       prefix="/facilities", tags=["grid"])
app.include_router(alerts.router,     prefix="/facilities", tags=["alerts"])
app.include_router(reports.router,    prefix="/facilities", tags=["reports"])
app.include_router(forecast.router,   prefix="/facilities", tags=["forecast"])
app.include_router(optimize.router,   prefix="/facilities", tags=["optimize"])
app.include_router(safety.router,     prefix="/facilities", tags=["safety"])
app.include_router(sim.router,        prefix="/api/v1",     tags=["simulation"])


@app.get("/health", tags=["health"])
async def health():
    # Always return 200 so Railway healthcheck passes
    # DB/Redis checked async — won't kill the deployment
    db_ok    = False
    redis_ok = False
    try:
        db_ok    = await ping_db()
    except Exception:
        pass
    try:
        redis_ok = await ping_redis()
    except Exception:
        pass
    status = "ok" if (db_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "version": settings.app_version,
        "db": db_ok,
        "redis": redis_ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/", tags=["health"])
async def root():
    return {"service": "MicroGrid AI API", "version": settings.app_version, "status": "running"}
