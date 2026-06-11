"""
Simulation / Edge bridge — endpoints for the Wokwi ESP32 (Prakriti Energy).

All edge endpoints require a per-device API key:  Authorization: Bearer dk_<id>_<secret>
The key is bound to one site_id — a stolen device can ONLY access its own site,
never another customer's data, commands, or forecast. Keys are revocable.

Device provisioning (/devices) is admin-only, protected by your JWT login.
The brain, data, and algorithm live server-side — the device holds only its key.
"""
import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import get_redis
from backend.core.database import get_db
from backend.core.security import CurrentUser, get_current_user, hash_api_key, verify_api_key
from backend.services.forecast_service import get_load_forecast

router = APIRouter()

DEFAULT_SITE = "sim-hospital-01"


# ── Per-device API-key auth ───────────────────────────────────────
# Every edge endpoint requires  Authorization: Bearer dk_<id>_<secret>
# and the key must belong to the site_id being accessed. A stolen device
# key can ONLY touch its own site — never another customer's data.

async def verify_device_key(authorization: Optional[str], site_id: str, db: AsyncSession) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing device API key",
                            headers={"WWW-Authenticate": "Bearer"})
    token = authorization[7:].strip()
    parts = token.split("_")
    if len(parts) != 3 or parts[0] != "dk":
        raise HTTPException(status_code=401, detail="Malformed device API key")
    key_id, secret = parts[1], parts[2]

    row = (await db.execute(
        text("SELECT site_id, key_hash, is_active FROM device_keys WHERE id = :id"),
        {"id": key_id},
    )).one_or_none()

    if row is None or not row.is_active or not verify_api_key(secret, row.key_hash):
        raise HTTPException(status_code=401, detail="Invalid or revoked device API key")
    if row.site_id != site_id:
        # Key is valid but for a DIFFERENT site → hard deny (no cross-tenant access)
        raise HTTPException(status_code=403, detail="Key not authorized for this site")

    # best-effort last-used stamp
    try:
        await db.execute(text("UPDATE device_keys SET last_used_at = now() WHERE id = :id"), {"id": key_id})
    except Exception:
        pass

# Default relay state when no command has been set yet (all on, DG + grid-charge off)
DEFAULT_COMMANDS = {
    "grid_relay":        True,
    "solar_relay":       True,
    "battery_relay":     True,
    "dg_relay":          False,
    "grid_charge_relay": False,
    "battery_discharge": False,   # brain releases the battery only when it pays (PEAK)
}

RESERVE_SOC     = 30.0   # outage-backup floor — savings never eat into this
SIM_BATTERY_KWH = 5.0    # Wokwi pack size (5 kWh)
PEAK_WINDOW_H   = 4.0    # evening peak duration the battery must carry

# ── Efficiency upgrade constants ──
SIM_CONTRACT_KW   = 8.0   # contract demand — spikes above this incur demand charges
OFFPEAK_RATE_RS   = 5.25  # cheapest grid energy (what stored kWh cost us)
CYCLE_COST_RS     = 2.5   # battery wear per kWh cycled (pack price / lifetime throughput)
CLOUDY_FACTOR     = 0.4   # weather factor below this = cloudy day expected
DIESEL_RATE_RS    = 25.0  # ₹/kWh equivalent cost of running DG


# ── Shadow savings calculator ────────────────────────────────────
# Runs on every telemetry ingest. Compares "what the brain decided" vs.
# "dumb baseline: buy everything from grid, no battery, no optimization."
# The delta is the ₹ the system saves (or would save in shadow/pilot mode).

def compute_interval_savings(payload: "SimTelemetry", dt_sim_h: float,
                             commands: dict) -> dict:
    """Return per-interval savings breakdown in ₹."""
    load_kwh = payload.total_load_w / 1000.0 * dt_sim_h
    tariff = payload.tariff_rs_kwh or 7.0

    # Baseline: all load bought from grid at current tariff
    baseline_cost = load_kwh * tariff

    # Solar savings: free energy displacing grid purchase
    solar_used_w = min(payload.solar_w, payload.total_load_w)
    solar_kwh = solar_used_w / 1000.0 * dt_sim_h
    solar_savings = solar_kwh * tariff

    # Arbitrage savings: battery discharging at peak displaces expensive grid
    # The stored energy was bought at off-peak rate, so the net saving is the spread
    arbitrage_savings = 0.0
    if commands.get("battery_discharge") and tariff > OFFPEAK_RATE_RS:
        deficit_w = max(0.0, payload.total_load_w - payload.solar_w)
        discharge_kwh = deficit_w / 1000.0 * dt_sim_h
        arbitrage_savings = discharge_kwh * (tariff - OFFPEAK_RATE_RS)

    # Demand shaving: avoiding monthly penalty from spikes above contract demand
    # ₹350/kVA/month ≈ ₹0.50/kW per interval (amortized). Conservative estimate:
    # each kW clipped saves ₹350/month ÷ 730 hours = ₹0.48/kWh
    demand_savings = 0.0
    if payload.total_load_w / 1000.0 > SIM_CONTRACT_KW and commands.get("battery_discharge"):
        clipped_kw = payload.total_load_w / 1000.0 - SIM_CONTRACT_KW
        demand_savings = clipped_kw * dt_sim_h * 0.48

    # DG displacement: battery displacing diesel (₹25/kWh vs ₹5.25 stored)
    dg_savings = 0.0
    if payload.dg_on and not payload.grid_on and commands.get("battery_discharge"):
        dg_displaced_kwh = min(payload.total_load_w, payload.solar_w + (payload.total_load_w - (payload.dg_w or 0))) / 1000.0 * dt_sim_h
        dg_savings = dg_displaced_kwh * (DIESEL_RATE_RS - OFFPEAK_RATE_RS)

    total_savings = solar_savings + arbitrage_savings + demand_savings + dg_savings

    return {
        "solar_rs": round(solar_savings, 4),
        "arbitrage_rs": round(arbitrage_savings, 4),
        "demand_rs": round(demand_savings, 4),
        "dg_rs": round(dg_savings, 4),
        "total_rs": round(total_savings, 4),
        "baseline_cost_rs": round(baseline_cost, 4),
        "optimized_cost_rs": round(baseline_cost - total_savings, 4),
        "load_kwh": round(load_kwh, 4),
        "dt_sim_h": round(dt_sim_h, 4),
    }


async def accumulate_savings(r, site_id: str, interval: dict) -> None:
    """Add interval savings to running Redis totals."""
    pipe = r.pipeline()
    pipe.hincrbyfloat(f"savings:{site_id}", "solar_rs", interval["solar_rs"])
    pipe.hincrbyfloat(f"savings:{site_id}", "arbitrage_rs", interval["arbitrage_rs"])
    pipe.hincrbyfloat(f"savings:{site_id}", "demand_rs", interval["demand_rs"])
    pipe.hincrbyfloat(f"savings:{site_id}", "dg_rs", interval["dg_rs"])
    pipe.hincrbyfloat(f"savings:{site_id}", "total_rs", interval["total_rs"])
    pipe.hincrbyfloat(f"savings:{site_id}", "baseline_cost_rs", interval["baseline_cost_rs"])
    pipe.hincrbyfloat(f"savings:{site_id}", "optimized_cost_rs", interval["optimized_cost_rs"])
    pipe.hincrbyfloat(f"savings:{site_id}", "load_kwh", interval["load_kwh"])
    pipe.hincrbyfloat(f"savings:{site_id}", "intervals", 1)
    pipe.hincrbyfloat(f"savings:{site_id}", "sim_hours", interval["dt_sim_h"])
    await pipe.execute()


def brain_decide(soc: float, solar_w: float, tariff_period: str, current: dict,
                 forecast: dict | None = None, load_w: float = 0.0,
                 tariff_rs: float = 7.0, dg_on: bool = False, grid_on: bool = True) -> dict:
    """The cloud brain — decides grid-charging from telemetry (ToD arbitrage).

    REACTIVE base + PREDICTIVE add-on:
      - Reactive: charge during cheap windows / when low, never at peak, stop at 90%.
      - Predictive: if a trustworthy forecast shows a load peak coming soon, pre-charge
        now (while power is cheap) so we don't buy that peak at peak price.

    The predictive branch only fires when forecast["available"] is True — i.e. once
    enough history exists. Until then the brain runs purely reactive. So it
    "auto-upgrades" to predictive with no code change once data accumulates.

    Only sets `grid_charge_relay`; preserves manual control of other relays.
    The ESP32 applies its own SAFETY overrides on top of this decision.
    """
    cmd = dict(current)
    cmd.pop("_brain", None)  # never persist diagnostic metadata into the command
    period = (tariff_period or "").upper()
    fc_ok = bool(forecast and forecast.get("available"))
    solar_next_kw = float((forecast or {}).get("solar_next_3h_kw") or 0)

    # ── Efficiency 1: charge TARGET sized by forecast, not blanket 90% ──
    # Store just enough for the peak window + outage reserve → fewer wasted
    # cycles, less standby loss, longer battery life.
    target_soc = 90.0
    if fc_ok:
        peak_kw = float(forecast.get("predicted_peak_kw") or 0)
        needed_pct = (peak_kw * PEAK_WINDOW_H / SIM_BATTERY_KWH) * 100.0
        target_soc = max(45.0, min(90.0, RESERVE_SOC + needed_pct))
        # ── Efficiency 4: weather-aware — cloudy tomorrow means solar won't
        # refill us for free, so bank more cheap grid energy tonight.
        wf = forecast.get("weather_solar_factor")
        if wf is not None and float(wf) < CLOUDY_FACTOR:
            target_soc = min(90.0, target_soc + 15.0)

    want_charge = False
    if soc < target_soc:
        # ── Reactive ──
        if period == "OFF-PEAK" and solar_w < 500:          # cheap power + no free solar → store
            # ── Efficiency 2: solar-aware hold — skip pre-dawn grid buying
            # when the forecast says the sun will fill us for free shortly.
            if not (solar_next_kw > 1.0 and soc >= RESERVE_SOC + 10):
                want_charge = True
        elif soc < 25 and period != "PEAK":                 # top up if low, but never at peak price
            want_charge = True

        # ── Predictive pre-charge ahead of a forecast load peak ──
        if fc_ok and period != "PEAK" and soc < min(80.0, target_soc):
            peak_in = forecast.get("peak_in_hours")
            peak_kw = float(forecast.get("predicted_peak_kw") or 0)
            if peak_in is not None and peak_in <= 4 and peak_kw > 6.0:
                want_charge = True

    # ── Efficiency 3: discharge ONLY when it pays — at PEAK, above reserve,
    # and only when the tariff spread beats battery wear (degradation guard).
    spread_ok = (tariff_rs - OFFPEAK_RATE_RS) > CYCLE_COST_RS
    discharge = (period == "PEAK") and soc > RESERVE_SOC and spread_ok

    # ── Efficiency 5: demand-charge shaving — clip load spikes above contract
    # demand at ANY hour. One 30-min spike sets the month's demand penalty,
    # so clipping it beats every energy-rate trick.
    if load_w / 1000.0 > SIM_CONTRACT_KW and soc > RESERVE_SOC:
        discharge = True

    # ── Efficiency 6: DG displacement — diesel costs ~Rs 25/kWh, the most
    # expensive power in the system. If the DG is carrying load, every kWh
    # the battery can give displaces diesel. Worth running below reserve
    # is NOT allowed (outage backup), but reserve-to-DG is always a win.
    if dg_on and not grid_on and soc > RESERVE_SOC:
        discharge = True

    cmd["grid_charge_relay"] = want_charge
    cmd["battery_discharge"] = discharge
    return cmd


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
    dg_w:               Optional[float] = 0.0
    circuits:           list[CircuitReading] = []


class RelayCommands(BaseModel):
    site_id:           Optional[str] = DEFAULT_SITE
    grid_relay:        bool = True
    solar_relay:       bool = True
    battery_relay:     bool = True
    dg_relay:          bool = False
    grid_charge_relay: bool = False
    battery_discharge: bool = False


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/ingest")
async def sim_ingest(payload: SimTelemetry, request: Request, db: AsyncSession = Depends(get_db)):
    """Receive telemetry from ESP32 → persist to Postgres + cache latest in Redis."""
    await verify_device_key(request.headers.get("authorization"), payload.site_id, db)
    circuits_json = json.dumps([c.model_dump() for c in payload.circuits])

    await db.execute(
        text("""
            INSERT INTO telemetry
                (site_id, ts, soc_pct, solar_w, total_load_w, sim_hour,
                 grid_charge_active, grid_charge_w, charge_source,
                 tariff_period, tariff_rs_kwh,
                 grid_on, battery_on, solar_on, dg_on, circuits)
            VALUES
                (:site_id, :ts, :soc_pct, :solar_w, :total_load_w, :sim_hour,
                 :grid_charge_active, :grid_charge_w, :charge_source,
                 :tariff_period, :tariff_rs_kwh,
                 :grid_on, :battery_on, :solar_on, :dg_on, CAST(:circuits AS JSONB))
        """),
        {
            "site_id": payload.site_id, "ts": payload.ts, "soc_pct": payload.soc_pct,
            "solar_w": payload.solar_w, "total_load_w": payload.total_load_w, "sim_hour": payload.sim_hour,
            "grid_charge_active": payload.grid_charge_active, "grid_charge_w": payload.grid_charge_w,
            "charge_source": payload.charge_source, "tariff_period": payload.tariff_period,
            "tariff_rs_kwh": payload.tariff_rs_kwh, "grid_on": payload.grid_on,
            "battery_on": payload.battery_on, "solar_on": payload.solar_on, "dg_on": payload.dg_on,
            "circuits": circuits_json,
        },
    )
    # get_db commits on success

    # Cache the latest reading + run the cloud brain to set the next command
    try:
        r = await get_redis()
        cached = payload.model_dump()
        cached["received_at"] = datetime.now(timezone.utc).isoformat()
        await r.set(f"latest:{payload.site_id}", json.dumps(cached, default=str))

        # ── Cloud brain decides grid-charging (reactive + predictive) ──
        forecast = await get_load_forecast(db, payload.site_id, payload.sim_hour)
        raw = await r.get(f"commands:{payload.site_id}")
        current = json.loads(raw) if raw else dict(DEFAULT_COMMANDS)
        decided = brain_decide(payload.soc_pct, payload.solar_w, payload.tariff_period, current, forecast,
                               load_w=payload.total_load_w, tariff_rs=payload.tariff_rs_kwh or 7.0,
                               dg_on=payload.dg_on, grid_on=payload.grid_on)
        await r.set(f"commands:{payload.site_id}", json.dumps(decided))

        # ── Shadow savings: compute what this interval saved vs. dumb baseline ──
        prev_raw = await r.get(f"prev_hour:{payload.site_id}")
        prev_hour = float(prev_raw) if prev_raw else None
        if prev_hour is not None and payload.sim_hour is not None:
            dt = (payload.sim_hour - prev_hour) % 24.0
            if 0 < dt < 1.0:  # sanity: skip if clock wrapped weirdly or first reading
                interval = compute_interval_savings(payload, dt, decided)
                await accumulate_savings(r, payload.site_id, interval)
        if payload.sim_hour is not None:
            await r.set(f"prev_hour:{payload.site_id}", str(payload.sim_hour))
    except Exception:
        pass  # cache/brain are best-effort; the ESP32 has local fallback

    return {"status": "ok", "ts": payload.ts}


@router.get("/commands/latest")
async def get_commands(request: Request, site_id: str = Query(default=DEFAULT_SITE),
                       db: AsyncSession = Depends(get_db)):
    """Return relay command state for the ESP32. Reads Redis commands:{site_id}."""
    await verify_device_key(request.headers.get("authorization"), site_id, db)
    try:
        r = await get_redis()
        val = await r.get(f"commands:{site_id}")
        if val:
            return json.loads(val)
    except Exception:
        pass
    return DEFAULT_COMMANDS


@router.post("/commands")
async def set_commands(cmd: RelayCommands, request: Request, db: AsyncSession = Depends(get_db)):
    """Dashboard → save relay commands to Redis commands:{site_id}."""
    site_id = cmd.site_id or DEFAULT_SITE
    await verify_device_key(request.headers.get("authorization"), site_id, db)
    state = {
        "grid_relay":        cmd.grid_relay,
        "solar_relay":       cmd.solar_relay,
        "battery_relay":     cmd.battery_relay,
        "dg_relay":          cmd.dg_relay,
        "grid_charge_relay": cmd.grid_charge_relay,
        "battery_discharge": cmd.battery_discharge,
    }
    try:
        r = await get_redis()
        await r.set(f"commands:{site_id}", json.dumps(state))
    except Exception:
        pass
    return {"status": "ok"}


# Backward-compatible alias (old sketch used PUT)
@router.put("/commands")
async def set_commands_put(cmd: RelayCommands, request: Request, db: AsyncSession = Depends(get_db)):
    return await set_commands(cmd, request, db)


@router.get("/forecast")
async def forecast(request: Request, site_id: str = Query(default=DEFAULT_SITE),
                   db: AsyncSession = Depends(get_db)):
    """The brain's current load forecast for a site (drives predictive dispatch)."""
    await verify_device_key(request.headers.get("authorization"), site_id, db)
    current_hour = None
    try:
        r = await get_redis()
        val = await r.get(f"latest:{site_id}")
        if val:
            current_hour = json.loads(val).get("sim_hour")
    except Exception:
        pass
    return await get_load_forecast(db, site_id, current_hour)


@router.get("/telemetry/latest")
async def get_latest_telemetry(request: Request, site_id: str = Query(default=DEFAULT_SITE),
                               db: AsyncSession = Depends(get_db)):
    """Debug — last reading the ESP32 sent for a site."""
    await verify_device_key(request.headers.get("authorization"), site_id, db)
    try:
        r = await get_redis()
        val = await r.get(f"latest:{site_id}")
        if val:
            return json.loads(val)
    except Exception:
        pass
    return {"status": "no_data", "message": "No telemetry received yet"}


# ── Device provisioning (admin only — protected by your JWT login) ────────

class DeviceCreate(BaseModel):
    site_id: str
    label: Optional[str] = None


@router.post("/devices", status_code=201)
async def create_device(body: DeviceCreate, db: AsyncSession = Depends(get_db),
                        current_user: CurrentUser = Depends(get_current_user)):
    """Mint a new per-device API key for a site. Returns the key ONCE — store it now."""
    current_user.require_admin()
    key_id = secrets.token_hex(6)
    secret = secrets.token_hex(24)
    token  = f"dk_{key_id}_{secret}"
    await db.execute(
        text("""INSERT INTO device_keys (id, site_id, key_hash, label)
                VALUES (:id, :site_id, :hash, :label)"""),
        {"id": key_id, "site_id": body.site_id, "hash": hash_api_key(secret), "label": body.label},
    )
    return {
        "key_id": key_id, "site_id": body.site_id,
        "api_key": token,
        "warning": "Store this now — it is not retrievable later.",
    }


@router.get("/devices")
async def list_devices(site_id: Optional[str] = Query(default=None),
                       db: AsyncSession = Depends(get_db),
                       current_user: CurrentUser = Depends(get_current_user)):
    current_user.require_admin()
    if site_id:
        rows = (await db.execute(
            text("SELECT id, site_id, label, is_active, created_at, last_used_at FROM device_keys WHERE site_id=:s ORDER BY created_at DESC"),
            {"s": site_id})).mappings().all()
    else:
        rows = (await db.execute(
            text("SELECT id, site_id, label, is_active, created_at, last_used_at FROM device_keys ORDER BY created_at DESC"))).mappings().all()
    return [dict(r) for r in rows]


@router.delete("/devices/{key_id}", status_code=204)
async def revoke_device(key_id: str, db: AsyncSession = Depends(get_db),
                        current_user: CurrentUser = Depends(get_current_user)):
    """Revoke a device key (e.g. lost/stolen controller). Only its site is affected."""
    current_user.require_admin()
    await db.execute(text("UPDATE device_keys SET is_active=false WHERE id=:id"), {"id": key_id})


# ── Dashboard-facing edge monitor (JWT auth, no device key needed) ───────

@router.get("/edge/live")
async def edge_live(site_id: str = Query(default=DEFAULT_SITE),
                    db: AsyncSession = Depends(get_db),
                    current_user: CurrentUser = Depends(get_current_user)):
    """Live edge telemetry + brain command + forecast in one call (for the dashboard)."""
    r = await get_redis()
    telemetry = commands = forecast_data = None
    try:
        val = await r.get(f"latest:{site_id}")
        if val:
            telemetry = json.loads(val)
    except Exception:
        pass
    try:
        val = await r.get(f"commands:{site_id}")
        if val:
            commands = json.loads(val)
    except Exception:
        pass
    try:
        forecast_data = await get_load_forecast(db, site_id, (telemetry or {}).get("sim_hour"))
    except Exception:
        pass
    savings = None
    try:
        raw = await r.hgetall(f"savings:{site_id}")
        if raw:
            savings = {k: round(float(v), 2) for k, v in raw.items()}
    except Exception:
        pass
    return {
        "telemetry": telemetry,
        "commands": commands or DEFAULT_COMMANDS,
        "forecast": forecast_data,
        "savings": savings,
    }


@router.get("/edge/savings")
async def edge_savings(site_id: str = Query(default=DEFAULT_SITE),
                       current_user: CurrentUser = Depends(get_current_user)):
    """Shadow savings running totals for a site."""
    try:
        r = await get_redis()
        raw = await r.hgetall(f"savings:{site_id}")
        if raw:
            return {k: round(float(v), 2) for k, v in raw.items()}
    except Exception:
        pass
    return {"total_rs": 0, "solar_rs": 0, "arbitrage_rs": 0, "demand_rs": 0, "dg_rs": 0,
            "baseline_cost_rs": 0, "optimized_cost_rs": 0, "load_kwh": 0, "intervals": 0, "sim_hours": 0}


@router.post("/edge/savings/reset")
async def reset_savings(site_id: str = Query(default=DEFAULT_SITE),
                        current_user: CurrentUser = Depends(get_current_user)):
    """Reset the shadow savings counter (e.g. start of a new pilot month)."""
    try:
        r = await get_redis()
        await r.delete(f"savings:{site_id}")
    except Exception:
        pass
    return {"status": "ok", "message": f"Savings counter reset for {site_id}"}
