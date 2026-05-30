
from datetime import datetime
from fastapi import FastAPI
import pandas as pd
import requests

app = FastAPI()

# In-memory storage

readings = []

@app.get("/")
def root():
return {
"status": "running",
"service": "MicroGrid AI Backend"
}

@app.post("/ingest")
def ingest(payload: dict):
"""
Receives feeder data every 15 minutes.
"""

```
required_fields = [
    "timestamp",
    "load_kw",
    "solar_kw",
    "battery_soc"
]

missing = [f for f in required_fields if f not in payload]

if missing:
    return {
        "status": "error",
        "missing_fields": missing
    }

readings.append(payload)

# Prevent unlimited memory growth
if len(readings) > 10000:
    del readings[:2000]

return {
    "status": "received",
    "records": len(readings)
}
```

@app.get("/data/count")
def data_count():
return {
"records": len(readings)
}

@app.get("/solar/health")
def solar_health_check():
# Your existing solar health code remains unchanged below
pass

