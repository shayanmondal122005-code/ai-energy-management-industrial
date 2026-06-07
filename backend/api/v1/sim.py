"""
Simulation / Edge bridge — endpoints for the Wokwi ESP32 (Prakriti Energy).

POST /api/v1/ingest           — ESP32 posts telemetry (no auth). Saved to Postgres + Redis.
GET  /api/v1/commands/latest  — ESP32 fetches relay command state (from Redis).
POST /api/v1/commands         — dashboard sends relay commands (to Redis).
GET  /api/v1/telemetry/latest — debug: last reading for a site (from Redis).

Unauthenticated by design — the ESP32 has no JWT. Separate from the production
/facilities/{id}/ingest flow so the sim runs without a tenant/facility.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import get_redis
from backend.core.database import get_db

router = APIRouter()

DEFAULT_SITE = "sim-hospital-01"

# Default relay state when no command has been set yet (all on, DG + grid-charge off)
DEFAULT_COMMANDS = {
    "grid_relay":        True,
    "solar_relay":       True,
    "battery_relay":     True,
    "dg_relay":          False,
    "grid_charge_relay": False,
}


# ── Schemas ───────────────────────────────────────────────────────

class CircuitReading(BaseModel):
    name:   str
    watts:  float
    active: bool


class SimTelemetry(BaseModel):
    site_id:            str
    ts:                 int
    soc_pct:            float
    solar_w:            float
    total_load_w:       float
    grid_charge_active: Optional[bool]  = False
    grid_charge_w:      Optional[float] = 0.0
    charge_source:      Optional[str]   = "none"
    tariff_period:      Optional[str]   = "UNKNOWN"
    tariff_rs_kwh:      Optional[float] = 0.0
    sim_hour:           Optional[float] = None
    grid_on:            bool = True
    battery_on:         bool = True
    solar_on:           bool = True
    dg_on:              bool = False
    circuits:           list[CircuitReading] = []


class RelayCommands(BaseModel):
    site_id:           Optional[str] = DEFAULT_SITE
    grid_relay:        bool = True
    solar_relay:       bool = True
    battery_relay:     bool = True
    dg_relay:          bool = False
    grid_charge_relay: bool = False


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/ingest")
async def sim_ingest(payload: SimTelemetry, db: AsyncSession = Depends(get_db)):
    """Receive telemetry from ESP32 → persist to Postgres + cache latest in Redis."""
    circuits_json = json.dumps([c.model_dump() for c in payload.circuits])

    await db.execute(
        text("""
            INSERT INTO telemetry
                (site_id, ts, soc_pct, solar_w, total_load_w,
                 grid_charge_active, grid_charge_w, charge_source,
                 tariff_period, tariff_rs_kwh,
                 grid_on, battery_on, solar_on, dg_on, circuits)
            VALUES
                (:site_id, :ts, :soc_pct, :solar_w, :total_load_w,
                 :grid_charge_active, :grid_charge_w, :charge_source,
                 :tariff_period, :tariff_rs_kwh,
                 :grid_on, :battery_on, :solar_on, :dg_on, CAST(:circuits AS JSONB))
        """),
        {
            "site_id": payload.site_id, "ts": payload.ts, "soc_pct": payload.soc_pct,
            "solar_w": payload.solar_w, "total_load_w": payload.total_load_w,
            "grid_charge_active": payload.grid_charge_active, "grid_charge_w": payload.grid_charge_w,
            "charge_source": payload.charge_source, "tariff_period": payload.tariff_period,
            "tariff_rs_kwh": payload.tariff_rs_kwh, "grid_on": payload.grid_on,
            "battery_on": payload.battery_on, "solar_on": payload.solar_on, "dg_on": payload.dg_on,
            "circuits": circuits_json,
        },
    )
    # get_db commits on success

    # Cache the latest reading in Redis
    try:
        r = await get_redis()
        cached = payload.model_dump()
        cached["received_at"] = datetime.now(timezone.utc).isoformat()
        await r.set(f"latest:{payload.site_id}", json.dumps(cached, default=str))
    except Exception:
        pass  # cache is best-effort

    return {"status": "ok", "ts": payload.ts}


@router.get("/commands/latest")
async def get_commands(site_id: str = Query(default=DEFAULT_SITE)):
    """Return relay command state for the ESP32. Reads Redis commands:{site_id}."""
    try:
        r = await get_redis()
        val = await r.get(f"commands:{site_id}")
        if val:
            return json.loads(val)
    except Exception:
        pass
    return DEFAULT_COMMANDS


@router.post("/commands")
async def set_commands(cmd: RelayCommands):
    """Dashboard → save relay commands to Redis commands:{site_id}."""
    site_id = cmd.site_id or DEFAULT_SITE
    state = {
        "grid_relay":        cmd.grid_relay,
        "solar_relay":       cmd.solar_relay,
        "battery_relay":     cmd.battery_relay,
        "dg_relay":          cmd.dg_relay,
        "grid_charge_relay": cmd.grid_charge_relay,
    }
    try:
        r = await get_redis()
        await r.set(f"commands:{site_id}", json.dumps(state))
    except Exception:
        pass
    return {"status": "ok"}


# Backward-compatible alias (old sketch used PUT)
@router.put("/commands")
async def set_commands_put(cmd: RelayCommands):
    return await set_commands(cmd)


@router.get("/telemetry/latest")
async def get_latest_telemetry(site_id: str = Query(default=DEFAULT_SITE)):
    """Debug — last reading the ESP32 sent for a site."""
    try:
        r = await get_redis()
        val = await r.get(f"latest:{site_id}")
        if val:
            return json.loads(val)
    except Exception:
        pass
    return {"status": "no_data", "message": "No telemetry received yet"}
