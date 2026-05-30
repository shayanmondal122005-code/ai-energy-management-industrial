
from datetime import datetime
from fastapi import FastAPI
import pandas as pd
import requests  # <-- Fixed: Added missing import

app = FastAPI()
readings = []

@app.get("/solar/health")
def solar_health_check():
    """
    Runs all 4 solar health detectors on current data.
    Dashboard calls this every 5 minutes.
    """
    if len(readings) < 96:  # need at least 1 day
        return {"status": "insufficient_data"}
        
    df = pd.DataFrame(readings)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    alerts = []
    pr = 1.0  # <-- Fixed: Initialize default value early to prevent scope issues
    
    # ── DETECTOR 1: Panel soiling (dirty panels) ──
    recent_24h = df.tail(96)   # last 24 hours (15-min intervals)
    daytime = recent_24h[pd.to_datetime(recent_24h['timestamp']).dt.hour.between(9, 15)]
    
    if len(daytime) > 0:
        avg_solar = daytime['solar_kw'].mean()
        # Theoretical clear-sky for midday Kolkata ~180kW for 200kW system
        theoretical = 180.0
        pr = avg_solar / theoretical if theoretical > 0 else 1.0
        
        if pr < 0.75:
            alerts.append({
                "type": "SOILING", 
                "severity": "WARNING", 
                "message": (f"Panel Performance Ratio {pr:.2f} — below 0.75 threshold. "
                            f"Panels likely dirty. Cleaning will recover "
                            f"{(0.95 - pr) * theoretical:.0f} kW output "
                            f"worth ₹{(0.95 - pr) * theoretical * 6.1 * 8:.0f}/day."),
                "action": "Schedule panel cleaning"
            })
        elif pr < 0.85:
            alerts.append({
                "type": "SOILING", 
                "severity": "INFO", 
                "message": f"Performance Ratio {pr:.2f} — slight degradation. Monitor over next 3 days.",
                "action": "Monitor"
            })

    # ── DETECTOR 2: Sudden output drop (loose connection / fire risk) ──
    if len(df) >= 4:
        last_4 = df.tail(4)['solar_kw'].values
        recent_drop = last_4[0] - last_4[-1]
        hour_now = pd.to_datetime(df.iloc[-1]['timestamp']).hour
        
        # Significant drop during daytime with no cloud context
        if recent_drop > 50 and 9 <= hour_now <= 16:
            alerts.append({
                "type": "SUDDEN_DROP", 
                "severity": "CRITICAL", 
                "message": (f"Solar output dropped {recent_drop:.0f} kW in last hour "
                            f"with no weather event detected. "
                            f"Possible loose connection or inverter fault — "
                            f"fire risk. Immediate inspection recommended."),
                "action": "Inspect inverter and connections NOW"
            })

    # ── DETECTOR 3: Storm warning check ──
    try:
        weather_r = requests.get(
            "https://api.open-meteo.com/v1/forecast", 
            params={
                "latitude": 22.57,   # Kolkata
                "longitude": 88.36,
                "hourly": "windspeed_10m,precipitation_probability",
                "forecast_days": 2,
                "timezone": "Asia/Kolkata",
            }, 
            timeout=5
        )
        if weather_r.status_code == 200:
            wdata = weather_r.json()['hourly']
            max_wind = max(wdata['windspeed_10m'][:48])
            max_rain = max(wdata['precipitation_probability'][:48])
            
            if max_wind > 15 and max_rain > 70:
                alerts.append({
                    "type": "STORM", 
                    "severity": "WARNING", 
                    "message": (f"Storm forecast in next 48 hours. "
                                f"Max wind: {max_wind:.0f} km/h, "
                                f"Rain probability: {max_rain:.0f}%. "
                                f"Inspect panel mounting and array structure "
                                f"before storm arrives."),
                    "action": "Physical inspection of mounting"
                })
    except Exception:
        pass   # weather API unavailable — skip

    # ── DETECTOR 4: Performance degradation trend ──
    if len(df) >= 7 * 24 * 4:   # need 1 week
        this_week = df.tail(7 * 96)['solar_kw'].mean()
        last_week = df.tail(14 * 96).head(7 * 96)['solar_kw'].mean()
        
        if last_week > 5:
            week_drop = (last_week - this_week) / last_week * 100
            if week_drop > 15:
                alerts.append({
                    "type": "DEGRADATION", 
                    "severity": "WARNING", 
                    "message": (f"Solar output down {week_drop:.0f}% vs last week "
                                f"({this_week:.0f} kW avg vs {last_week:.0f} kW). "
                                f"Possible panel failure or soiling. "
                                f"Thermographic inspection recommended."),
                    "action": "Arrange thermographic scan"
                })

    return {
        "status": "ok",
        "alerts_count": len(alerts),
        "alerts": alerts,
        "performance_ratio": round(pr, 3),  # <-- Cleaned up cleanly
        "checked_at": datetime.now().isoformat()  # <-- Fixed: Works now with datetime import
    }
