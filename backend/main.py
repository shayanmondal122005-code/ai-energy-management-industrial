from datetime import datetime

from fastapi import FastAPI
import pandas as pd
import requests


app = FastAPI()

# In-memory storage
readings = []


@app.get("/")
def root():
    return {"status": "running", "service": "MicroGrid AI Backend"}


@app.post("/ingest")
def ingest(payload: dict):
    """
    Receives feeder data every 15 minutes.
    """
    required_fields = ["timestamp", "load_kw", "solar_kw", "battery_soc"]
    missing = [field for field in required_fields if field not in payload]

    if missing:
        return {"status": "error", "missing_fields": missing}

    readings.append(payload)

    # Prevent unlimited memory growth.
    if len(readings) > 10000:
        del readings[:2000]

    return {"status": "received", "records": len(readings)}


@app.get("/data/count")
def data_count():
    return {"records": len(readings)}


@app.get("/solar/health")
def solar_health_check():
    """
    Runs all 4 solar health detectors on current data.
    """
    if len(readings) < 96:
        return {"status": "insufficient_data", "alerts": []}

    df = pd.DataFrame(readings)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    alerts = []
    pr = 1.0

    # DETECTOR 1: Panel soiling / dirty panels
    recent_24h = df.tail(96)
    daytime = recent_24h[
        pd.to_datetime(recent_24h["timestamp"]).dt.hour.between(9, 15)
    ]

    if len(daytime) > 0:
        avg_solar = daytime["solar_kw"].mean()
        theoretical = 180.0
        pr = avg_solar / theoretical if theoretical > 0 else 1.0

        if pr < 0.75:
            alerts.append(
                {
                    "type": "SOILING",
                    "severity": "WARNING",
                    "message": (
                        f"Panel Performance Ratio {pr:.2f} below 0.75 threshold. "
                        "Panels likely dirty."
                    ),
                    "action": "Schedule panel cleaning",
                }
            )
        elif pr < 0.85:
            alerts.append(
                {
                    "type": "SOILING",
                    "severity": "INFO",
                    "message": (
                        f"Performance Ratio {pr:.2f} - slight degradation noticed."
                    ),
                    "action": "Monitor over next 3 days",
                }
            )

    # DETECTOR 2: Sudden output drop
    if len(df) >= 4:
        last_4 = df.tail(4)["solar_kw"].values
        recent_drop = last_4[0] - last_4[-1]
        hour_now = pd.to_datetime(df.iloc[-1]["timestamp"]).hour

        if recent_drop > 50 and 9 <= hour_now <= 16:
            alerts.append(
                {
                    "type": "SUDDEN_DROP",
                    "severity": "CRITICAL",
                    "message": (
                        f"Solar output dropped {recent_drop:.0f} kW rapidly during "
                        "daylight hours without weather variance."
                    ),
                    "action": "Inspect inverter links immediately",
                }
            )

    # DETECTOR 3: Storm warning check
    try:
        weather_r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 22.57,
                "longitude": 88.36,
                "hourly": "windspeed_10m,precipitation_probability",
                "forecast_days": 2,
                "timezone": "Asia/Kolkata",
            },
            timeout=5,
        )

        if weather_r.status_code == 200:
            wdata = weather_r.json()["hourly"]
            max_wind = max(wdata["windspeed_10m"][:48])
            max_rain = max(wdata["precipitation_probability"][:48])

            if max_wind > 15 and max_rain > 70:
                alerts.append(
                    {
                        "type": "STORM",
                        "severity": "WARNING",
                        "message": (
                            f"Storm forecast incoming. Max wind: {max_wind:.0f} km/h, "
                            f"Rain probability: {max_rain:.0f}%."
                        ),
                        "action": "Physical structural mounting check",
                    }
                )
    except Exception:
        pass

    return {
        "status": "ok",
        "alerts_count": len(alerts),
        "alerts": alerts,
        "performance_ratio": round(pr, 3),
        "checked_at": datetime.now().isoformat(),
    }
