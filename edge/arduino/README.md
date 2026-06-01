# MicroGrid AI — Arduino Edge Controller

## Hardware Required

| Component | Model | Cost | Purpose |
|---|---|---|---|
| Main controller | Arduino Mega 2560 | ₹800 | Runs all logic |
| WiFi bridge | ESP8266 NodeMCU / Wemos D1 Mini | ₹300 | Cloud communication |
| Load current | SCT-013-100 CT sensor | ₹400 | Measures kW |
| Grid voltage | ZMPT101B module | ₹300 | Measures grid V |
| Battery voltage | Voltage divider (10k+2.2k resistors) | ₹10 | Measures SoC |
| Battery current | ACS712 30A module | ₹200 | Charge/discharge |
| Temperature | DS18B20 waterproof | ₹150 | Battery temp |
| Real-time clock | DS3231 module | ₹200 | Timestamps offline |
| SD card | SD module + 8GB card | ₹300 | Local data logging |
| Display | 20x4 I2C LCD | ₹350 | Live status |
| Relay board | 8-channel 12V relay | ₹600 | Load control |
| Power supply | 12V 2A DIN-rail PSU | ₹800 | Powers controller |
| Enclosure | IP65 DIN-rail box | ₹1,500 | Industrial protection |
| **Total** | | **~₹6,000** | |

---

## What Happens When Internet Cuts

```
Internet OK:
  Arduino reads sensors → ESP8266 sends to cloud every 60s
  Cloud runs LP optimizer → sends CHARGE/DISCHARGE/HOLD command
  Arduino applies command to battery inverter via relay

Internet CUT (ESP8266 stops responding):
  Arduino detects: no response for 60s → switches to OFFLINE mode
  Local rules run every 15 seconds:
    SoC < 20%  → force CHARGE + shed P4/P5
    10am-4pm   → CHARGE (cheap hours)
    6pm-11pm   → DISCHARGE (peak hours)
    Otherwise  → HOLD

Internet returns:
  ESP8266 flushes buffered readings to cloud (up to 96 readings = 24h)
  Cloud schedule re-syncs
  Arduino switches back to NORMAL mode
```

---

## Safety — What CANNOT Be Overridden

Even if a bug, hacker, or broken cloud command tries to:

| Attempt | What Arduino does |
|---|---|
| Shed P1 loads (ICU/OT) | **Silently ignored in code** |
| Command when SoC < 12% | Overridden — forces CHARGE |
| Command when temp > 45°C | Overridden — forces HOLD + grid |
| Any command during SAFE mode | Blocked until fault cleared |

Hardware watchdog (WDT): if Arduino code freezes for 8 seconds,
it automatically restarts — returns to safe defaults.

---

## Libraries to Install

In Arduino IDE: Tools → Manage Libraries → search and install:
- `DallasTemperature` by Miles Burton
- `OneWire` by Jim Studt
- `RTClib` by Adafruit
- `SD` (built-in)
- `LiquidCrystal I2C` by Frank de Brabander
- `ArduinoJson` by Benoit Blanchon (for ESP8266)
- `ESP8266HTTPClient` (built-in with ESP8266 board package)

---

## Flashing

1. Flash `microgrid_local.ino` to **Arduino Mega**
2. Edit `esp8266_bridge.ino`: fill in WiFi credentials + backend URL + facility ID + API key
3. Flash `esp8266_bridge.ino` to **ESP8266 NodeMCU**
4. Wire TX/RX between them (cross: Mega TX1→ESP RX, Mega RX1→ESP TX)

---

## SD Card Log Format

Daily files: `YYYYMMDD.csv`
```
timestamp,load_kw,battery_soc,battery_temp,grid_voltage,net_kw,mode,battery_cmd
2026-06-01T10:30:00,312.4,68.2,31.5,231.4,-162.4,OFFLINE,CHARGE
```

Fault log: `FAULTS.txt`
```
[2026-06-01T18:32:11] SOC_CRITICAL: Battery at 11% — emergency grid import
```
