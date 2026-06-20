"""MicroGrid AI — laptop feeder (meter stand-in).

Plays the role of the on-site meter + plant while you have no hardware yet:
simulates a small hospital microgrid (solar curve, battery via Coulomb counting,
ToD tariff), POSTs telemetry to the backend, reads the cloud brain's relay
decision back, and applies it to the simulated battery — a full closed loop.

The ESP32 separately polls the same command and lights an LED, so you SEE the
brain's decision on real hardware.

Run:
    pip install requests
    python laptop_feeder.py

Stop with Ctrl-C. Watch the printed SoC / tariff / brain decision each tick.
"""
import math
import time
from datetime import datetime, timezone

import requests

# ── Config — match your ESP32 sketch ────────────────────────────
BASE_URL   = "https://ai-energy-management-industrial-production.up.railway.app"
SITE_ID    = "sim-hospital-01"
DEVICE_KEY = "dk_102bf365db58_17fe6b122c568ccc034a5f1fc83ce6fc68f97043baa8d45b"  # sim-hospital-01 demo key — ROTATE before any real pilot

TICK_SECONDS = 3.0     # real seconds between posts
SIM_STEP_H   = 0.5     # sim-hours advanced each tick → full day in ~2.5 min
START_HOUR   = 22.0    # begin just before off-peak so charging kicks in fast

# ── Plant constants (small demo site, same scale as the Wokwi sim) ──
BATTERY_WH      = 5000.0
SOLAR_PEAK_W    = 4000.0
MAX_CHARGE_W    = 1500.0
MAX_DISCHARGE_W = 2000.0
BASE_LOAD_W     = 2500.0
PEAK_LOAD_W     = 6500.0   # evening spike

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {DEVICE_KEY}",
    "Content-Type": "application/json",
})

soc = 55.0          # %
sim_hour = START_HOUR


def tariff(h: float):
    if h >= 23.0 or h < 6.0:        return "OFF-PEAK", 5.25
    if 18.0 <= h < 22.0:           return "PEAK", 9.50
    return "NORMAL", 7.00


def solar_w(h: float) -> float:
    if 6.0 <= h < 18.0:
        return max(0.0, SOLAR_PEAK_W * math.sin(math.pi * (h - 6.0) / 12.0))
    return 0.0


def load_w(h: float) -> float:
    return PEAK_LOAD_W if 18.0 <= h < 22.0 else BASE_LOAD_W


def post_telemetry(period, rs, sol, ld) -> bool:
    body = {
        "site_id": SITE_ID,
        "ts": int(time.time()),
        "soc_pct": round(soc, 1),
        "solar_w": round(sol),
        "total_load_w": round(ld),
        "tariff_period": period,
        "tariff_rs_kwh": rs,
        "sim_hour": round(sim_hour, 2),
        "grid_on": True, "battery_on": True, "solar_on": True, "dg_on": False,
    }
    try:
        r = session.post(f"{BASE_URL}/api/v1/ingest", json=body, timeout=10)
        return r.status_code == 200
    except requests.RequestException as e:
        print(f"  post error: {e}")
        return False


def get_commands() -> dict:
    try:
        r = session.get(f"{BASE_URL}/api/v1/commands/latest?site_id={SITE_ID}", timeout=10)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException as e:
        print(f"  command error: {e}")
    return {}


def main():
    global soc, sim_hour
    print(f"Laptop feeder -> {BASE_URL}  site={SITE_ID}")
    print("Ctrl-C to stop.\n")
    while True:
        period, rs = tariff(sim_hour)
        sol, ld = solar_w(sim_hour), load_w(sim_hour)

        ok = post_telemetry(period, rs, sol, ld)
        cmd = get_commands()
        charging   = bool(cmd.get("grid_charge_relay"))
        discharging = bool(cmd.get("battery_discharge"))

        # Apply the brain's decision to the simulated battery (Coulomb counting)
        charge_w = (sol - ld if sol > ld else 0.0)            # solar soak
        if charging:    charge_w += MAX_CHARGE_W
        discharge_w = MAX_DISCHARGE_W if (discharging and ld > sol) else 0.0
        d_soc = (charge_w - discharge_w) * (SIM_STEP_H) / BATTERY_WH * 100.0
        # Band SoC to 20-90% for battery longevity (avoid 100% hold / deep discharge),
        # same spirit as the real optimizer's 15-95% limits.
        soc = max(20.0, min(90.0, soc + d_soc))

        act = "CHARGE" if charging else "DISCHARGE" if discharging else "hold"
        flag = "ok" if ok else "POST FAILED"
        print(f"h={sim_hour:4.1f} {period:8s} Rs{rs:>4} | load {ld/1000:4.1f}kW "
              f"solar {sol/1000:4.1f}kW | SoC {soc:5.1f}% | brain: {act:9s} [{flag}]")

        sim_hour = (sim_hour + SIM_STEP_H) % 24.0
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped.")
