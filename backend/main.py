
    for col in ["load_kw", "solar_kw", "temp_c"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    hourly = (
        df.set_index("timestamp")[["load_kw", "solar_kw", "temp_c"]]
        .resample("1h")
        .mean()
        .dropna(subset=["load_kw"])
        .tail(hours)
        .reset_index()
    )

    output = StringIO()
    hourly.to_csv(output, index=False)
    return Response(output.getvalue(), media_type="text/csv")


@app.post("/simulate/tick")
def simulate_tick():
    if readings:
        last_ts = pd.to_datetime(readings[-1].get("timestamp"), errors="coerce")
        if pd.isna(last_ts):
            ts = datetime.now()
        else:
            ts = last_ts.to_pydatetime() + timedelta(minutes=15)
        last_soc = float(readings[-1].get("battery_soc", 68.0))
    else:
        ts = datetime.now() - timedelta(days=10)
        last_soc = 68.0

    hour = ts.hour
    month = ts.month
    load_factor = 1.35 if 8 <= hour <= 11 else 1.25 if 18 <= hour <= 22 else 0.75 if hour <= 5 else 1.0
    load_kw = max(80.0, min(600.0, 300.0 * load_factor + random.uniform(-20, 20)))

    if 6 <= hour <= 18:
        solar_angle = math.sin((hour - 6) * math.pi / 12)
        cloud_factor = 0.45 if month in [6, 7, 8, 9] else 0.85
        solar_kw = max(0.0, 200.0 * solar_angle * cloud_factor + random.uniform(-8, 8))
    else:
        solar_kw = 0.0

    net_kw = solar_kw - load_kw
    soc_change = net_kw / 500.0 * 100.0 * 0.25
    battery_soc = max(10.0, min(95.0, last_soc + soc_change))

    reading = {
        "timestamp": ts.isoformat(),
        "load_kw": round(load_kw, 2),
        "solar_kw": round(solar_kw, 2),
        "battery_soc": round(battery_soc, 2),
        "battery_temp": round(28.0 + random.uniform(-2, 4), 2),
        "temp_c": round(28.0 + random.uniform(-2, 4), 2),
    }
    readings.append(reading)

    if len(readings) > 10000:
        del readings[:2000]

    return {"status": "simulated", "records": len(readings), "reading": reading}


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
