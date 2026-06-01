"""XGBoost 24h load forecasting service.
Migrated from load_forecaster.py + data_loader.py.
Physics and feature engineering are correct — do not modify.
"""
import io
import logging
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

logger = logging.getLogger(__name__)

FEATURES = [
    "hour", "dayofweek", "month", "quarter",
    "is_weekend", "is_morning_peak", "is_evening_peak",
    "load_lag_1h", "load_lag_24h", "load_lag_168h",
    "load_rolling_3h", "load_rolling_24h",
    "temp_c", "is_tod_cheap",
]

XGBOOST_PARAMS = {
    "n_estimators"    : 500,
    "max_depth"       : 6,
    "learning_rate"   : 0.05,
    "subsample"       : 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 3,
    "random_state"    : 42,
    "verbosity"       : 0,
}


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag + rolling + calendar features. Preserves original logic exactly."""
    d = df.copy()
    d["hour"]              = d.index.hour
    d["dayofweek"]         = d.index.dayofweek
    d["month"]             = d.index.month
    d["quarter"]           = d.index.quarter
    d["is_weekend"]        = (d.index.dayofweek >= 5).astype(int)
    d["is_morning_peak"]   = d["hour"].between(8, 11).astype(int)
    d["is_evening_peak"]   = d["hour"].between(18, 22).astype(int)
    d["is_tod_cheap"]      = d["hour"].between(10, 16).astype(int)
    d["load_lag_1h"]       = d["load_kw"].shift(1)
    d["load_lag_24h"]      = d["load_kw"].shift(24)
    d["load_lag_168h"]     = d["load_kw"].shift(168)
    d["load_rolling_3h"]   = d["load_kw"].rolling(3).mean()
    d["load_rolling_24h"]  = d["load_kw"].rolling(24).mean()
    return d.dropna()


def train_load_model(df: pd.DataFrame) -> tuple[xgb.XGBRegressor, float, float]:
    """Train XGBoost on historical data. Returns (model, mae, mape)."""
    df_clean = df[FEATURES + ["load_kw"]].dropna()
    if len(df_clean) < 48:
        raise ValueError(f"Need at least 48 rows, got {len(df_clean)}")

    split = int(len(df_clean) * 0.8)
    X_tr, y_tr = df_clean[FEATURES].iloc[:split], df_clean["load_kw"].iloc[:split]
    X_te, y_te = df_clean[FEATURES].iloc[split:], df_clean["load_kw"].iloc[split:]

    model = xgb.XGBRegressor(**XGBOOST_PARAMS)
    model.fit(X_tr, y_tr)

    preds = np.clip(model.predict(X_te), 0, None)
    mae   = float(mean_absolute_error(y_te, preds))
    mape  = float(np.mean(np.abs((y_te - preds) / y_te.clip(lower=1))) * 100)

    logger.info("Model trained: MAE=%.1f kW, MAPE=%.1f%%", mae, mape)
    return model, mae, mape


def predict_next_24h(model: xgb.XGBRegressor, recent_df: pd.DataFrame) -> pd.DataFrame:
    """Generate 24h forecast. recent_df must have at least 168 rows with time features."""
    df_tmp = recent_df.copy()
    forecasts = []

    for step in range(24):
        nxt = df_tmp.index[-1] + pd.Timedelta(hours=1)
        row = {
            "hour"            : nxt.hour,
            "dayofweek"       : nxt.dayofweek,
            "month"           : nxt.month,
            "quarter"         : nxt.quarter,
            "is_weekend"      : int(nxt.dayofweek >= 5),
            "is_morning_peak" : int(8 <= nxt.hour <= 11),
            "is_evening_peak" : int(18 <= nxt.hour <= 22),
            "is_tod_cheap"    : int(10 <= nxt.hour <= 16),
            "load_lag_1h"     : df_tmp["load_kw"].iloc[-1],
            "load_lag_24h"    : df_tmp["load_kw"].iloc[-24] if len(df_tmp) >= 24 else df_tmp["load_kw"].mean(),
            "load_lag_168h"   : df_tmp["load_kw"].iloc[-168] if len(df_tmp) >= 168 else df_tmp["load_kw"].mean(),
            "load_rolling_3h" : df_tmp["load_kw"].iloc[-3:].mean(),
            "load_rolling_24h": df_tmp["load_kw"].iloc[-24:].mean(),
            "temp_c"          : df_tmp["temp_c"].iloc[-1] if "temp_c" in df_tmp.columns else 28.0,
        }
        X = pd.DataFrame([row])[FEATURES]
        pred = float(np.clip(model.predict(X)[0], 0, None))
        forecasts.append({"timestamp": nxt, "forecast_kw": round(pred, 1)})

        new_row = pd.DataFrame({"load_kw": [pred], "temp_c": [row["temp_c"]]}, index=[nxt])
        df_tmp = pd.concat([df_tmp, new_row])

    return pd.DataFrame(forecasts).set_index("timestamp")


def readings_to_dataframe(readings: list[Any]) -> pd.DataFrame:
    """Convert list of Reading ORM objects → DataFrame ready for forecasting."""
    rows = []
    for r in readings:
        rows.append({
            "timestamp"  : getattr(r, "timestamp", None) or r.get("timestamp"),
            "load_kw"    : float(getattr(r, "load_kw", 0) or r.get("load_kw", 0)),
            "solar_kw"   : float(getattr(r, "solar_kw", 0) or r.get("solar_kw", 0)),
            "battery_soc": float(getattr(r, "battery_soc", 0) or r.get("battery_soc", 0)),
            "temp_c"     : float(getattr(r, "battery_temp", 28) or r.get("temp_c", 28) or 28),
        })
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").set_index("timestamp")
    df = df.resample("1h").mean().dropna(subset=["load_kw"])
    return df
