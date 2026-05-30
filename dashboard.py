 # dashboard.py
# MicroGrid AI — Complete Production Dashboard
# India-native energy intelligence platform
# Run: streamlit run dashboard.py

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import xgboost as xgb
from sklearn.metrics import mean_absolute_error
import requests
import warnings
warnings.filterwarnings('ignore')

# ════════════════════════════════════════════════════════
# PAGE CONFIG — must be first streamlit call
# ════════════════════════════════════════════════════════

st.set_page_config(
    page_title="MicroGrid AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ════════════════════════════════════════════════════════
# STYLING
# ════════════════════════════════════════════════════════

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Background */
.stApp {
    background: #080c14;
}

/* Hide streamlit branding */
#MainMenu, footer, header { visibility: hidden; }

/* Metric cards */
div[data-testid="metric-container"] {
    background: linear-gradient(135deg, #0d1220 0%, #111827 100%);
    border: 1px solid #1e2d45;
    border-radius: 12px;
    padding: 20px 16px;
    position: relative;
    overflow: hidden;
}
div[data-testid="metric-container"]::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #3b82f6, #10b981);
}
div[data-testid="metric-container"] label {
    color: #4a6fa5 !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    letter-spacing: 1.5px !important;
    text-transform: uppercase !important;
}
div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
    color: #e2e8f0 !important;
    font-size: 26px !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
}
div[data-testid="metric-container"] div[data-testid="stMetricDelta"] {
    font-size: 12px !important;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #0a0e1a;
    border-right: 1px solid #1e2d45;
}
section[data-testid="stSidebar"] * {
    color: #94a3b8;
}

/* Divider */
hr {
    border-color: #1e2d45;
    margin: 1.5rem 0;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #1d4ed8, #1e40af);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 500;
    padding: 8px 20px;
    width: 100%;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    transform: translateY(-1px);
}

/* Select boxes and sliders */
.stSelectbox > div > div,
.stSlider > div {
    background: #0d1220;
    border-color: #1e2d45;
}

/* File uploader */
.stFileUploader {
    background: #0d1220;
    border: 1px dashed #1e2d45;
    border-radius: 8px;
    padding: 10px;
}

/* Custom alert classes */
.alert-critical {
    background: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.3);
    border-left: 3px solid #ef4444;
    border-radius: 8px;
    padding: 12px 16px;
    color: #fca5a5;
    font-size: 13px;
    margin: 6px 0;
    font-family: 'Inter', sans-serif;
}
.alert-warning {
    background: rgba(245,158,11,0.08);
    border: 1px solid rgba(245,158,11,0.25);
    border-left: 3px solid #f59e0b;
    border-radius: 8px;
    padding: 12px 16px;
    color: #fcd34d;
    font-size: 13px;
    margin: 6px 0;
}
.alert-info {
    background: rgba(59,130,246,0.08);
    border: 1px solid rgba(59,130,246,0.25);
    border-left: 3px solid #3b82f6;
    border-radius: 8px;
    padding: 12px 16px;
    color: #93c5fd;
    font-size: 13px;
    margin: 6px 0;
}
.alert-ok {
    background: rgba(16,185,129,0.08);
    border: 1px solid rgba(16,185,129,0.25);
    border-left: 3px solid #10b981;
    border-radius: 8px;
    padding: 12px 16px;
    color: #6ee7b7;
    font-size: 13px;
    margin: 6px 0;
}

/* Section headers */
.section-label {
    font-size: 10px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #1d4ed8;
    font-weight: 600;
    margin: 28px 0 6px;
    padding-bottom: 10px;
    border-bottom: 1px solid #1e2d45;
}

/* Page title */
.page-title {
    font-size: 28px;
    font-weight: 700;
    color: #e2e8f0;
    margin: 0;
    letter-spacing: -0.5px;
}
.page-subtitle {
    font-size: 13px;
    color: #4a6fa5;
    margin: 4px 0 20px;
    font-family: 'JetBrains Mono', monospace;
}

/* Live badge */
.live-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(16,185,129,0.1);
    border: 1px solid rgba(16,185,129,0.3);
    border-radius: 100px;
    padding: 3px 10px;
    font-size: 11px;
    color: #10b981;
    font-weight: 500;
}
.live-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #10b981;
    animation: pulse 2s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
}

/* Savings card */
.savings-card {
    background: linear-gradient(135deg, #0d2137 0%, #0a1628 100%);
    border: 1px solid #1e3a5f;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}
.savings-amount {
    font-size: 32px;
    font-weight: 700;
    color: #10b981;
    letter-spacing: -1px;
}
.savings-label {
    font-size: 11px;
    color: #4a6fa5;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 4px;
}

/* Model accuracy badge */
.accuracy-badge {
    background: linear-gradient(135deg, #1a1d2e, #0d1220);
    border: 1px solid #2d3561;
    border-radius: 8px;
    padding: 10px 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: 6px 0;
    font-size: 12px;
    color: #94a3b8;
}

/* Decision tag */
.decision-tag {
    display: inline-block;
    font-size: 10px;
    padding: 3px 10px;
    border-radius: 100px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin: 2px;
}
.tag-charge  { background: rgba(59,130,246,0.15); color: #60a5fa; border: 1px solid rgba(59,130,246,0.3); }
.tag-hold    { background: rgba(16,185,129,0.12); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }
.tag-shave   { background: rgba(245,158,11,0.12); color: #fbbf24; border: 1px solid rgba(245,158,11,0.3); }
.tag-critical{ background: rgba(239,68,68,0.15);  color: #f87171; border: 1px solid rgba(239,68,68,0.3); }

</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════

INDIA_TARIFFS = {
    "West Bengal — CESC": {
        "cheap_rate"          : 4.20,
        "normal_rate"         : 6.10,
        "peak_rate"           : 7.85,
        "demand_charge_per_kw": 320,
        "tod_cheap_hours"     : list(range(10, 16)),
        "tod_peak_hours"      : list(range(18, 23)),
    },
    "Maharashtra — MSEDCL": {
        "cheap_rate"          : 3.80,
        "normal_rate"         : 5.90,
        "peak_rate"           : 8.20,
        "demand_charge_per_kw": 280,
        "tod_cheap_hours"     : list(range(10, 16)),
        "tod_peak_hours"      : list(range(18, 22)),
    },
    "Tamil Nadu — TANGEDCO": {
        "cheap_rate"          : 4.50,
        "normal_rate"         : 6.40,
        "peak_rate"           : 8.10,
        "demand_charge_per_kw": 350,
        "tod_cheap_hours"     : list(range(10, 17)),
        "tod_peak_hours"      : list(range(18, 23)),
    },
    "Karnataka — BESCOM": {
        "cheap_rate"          : 4.10,
        "normal_rate"         : 6.00,
        "peak_rate"           : 7.70,
        "demand_charge_per_kw": 295,
        "tod_cheap_hours"     : list(range(10, 16)),
        "tod_peak_hours"      : list(range(18, 22)),
    },
    "Delhi — BSES/TPDDL": {
        "cheap_rate"          : 3.90,
        "normal_rate"         : 5.80,
        "peak_rate"           : 7.50,
        "demand_charge_per_kw": 260,
        "tod_cheap_hours"     : list(range(10, 16)),
        "tod_peak_hours"      : list(range(17, 22)),
    },
}

PLOT_COLORS = {
    "load"      : "#ef4444",
    "solar"     : "#f59e0b",
    "forecast"  : "#3b82f6",
    "soc"       : "#10b981",
    "grid"      : "#8b5cf6",
    "confidence": "rgba(59,130,246,0.08)",
    "grid_line" : "#1a2235",
    "bg"        : "#080c14",
    "panel"     : "#0d1220",
}

FEATURES = [
    'hour_sin','hour_cos','dow_sin','dow_cos',
    'month_sin','month_cos','quarter',
    'is_weekend','is_monsoon','is_summer',
    'is_morning_peak','is_evening_peak',
    'is_tod_cheap','is_night',
    'load_lag_1h','load_lag_2h','load_lag_3h',
    'load_lag_6h','load_lag_12h',
    'load_lag_24h','load_lag_48h','load_lag_168h',
    'load_roll_3h','load_roll_6h',
    'load_roll_24h','load_roll_std_24h',
    'solar_lag_24h','cloud_factor',
    'temp_c','temp_roll_6h',
    'peak_x_monsoon','peak_x_summer',
]


# ════════════════════════════════════════════════════════
# DATA GENERATION
# ════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False)
def generate_hospital_data(n_days=365, seed=42,
                            avg_kw=300, peak_kw=460,
                            solar_kw=200):
    """
    Generates realistic Indian hospital energy data.
    Calibrated to match real BEE audit profiles.
    Includes monsoon, seasonal, and ToD patterns.
    """
    np.random.seed(seed)
    hours = pd.date_range(
        pd.Timestamp.now() - pd.Timedelta(days=n_days),
        periods=n_days * 24,
        freq='1h'
    )

    load_list, solar_list, temp_list = [], [], []

    for ts in hours:
        h, m, dow = ts.hour, ts.month, ts.dayofweek

        # Time-of-day load pattern
        if   0  <= h <= 5:  factor = 0.72
        elif 6  <= h <= 7:  factor = 0.85
        elif 8  <= h <= 11: factor = 1.38
        elif 12 <= h <= 13: factor = 1.15
        elif 14 <= h <= 16: factor = 1.05
        elif 17 <= h <= 17: factor = 1.10
        elif 18 <= h <= 22: factor = 1.25
        else:               factor = 0.95

        if m in [4, 5, 6]:   factor *= 1.16
        if m in [7, 8, 9]:   factor *= 1.10
        if dow >= 5:          factor *= 0.90

        base = avg_kw * factor
        load_list.append(
            float(np.clip(base + np.random.normal(0, avg_kw * 0.07),
                          avg_kw * 0.50, peak_kw * 1.05))
        )

        # Solar — Kolkata profile with monsoon
        if 6 <= h <= 18:
            angle = np.sin((h - 6) * np.pi / 12)
            s = solar_kw * angle
            if   m in [6, 7, 8, 9]: s *= float(np.random.beta(1.5, 5))
            elif m in [12, 1, 2]:   s *= float(np.random.beta(8, 2))
            else:                    s *= float(np.random.beta(7, 2))
            solar_list.append(max(0.0, s + np.random.normal(0, 8)))
        else:
            solar_list.append(0.0)

        t = 28 + 8 * np.sin((m - 4) * np.pi / 6)
        temp_list.append(t + np.random.normal(0, 1.5))

    return pd.DataFrame({
        'load_kw' : load_list,
        'solar_kw': solar_list,
        'temp_c'  : temp_list,
    }, index=hours)


# ════════════════════════════════════════════════════════
# FEATURE ENGINEERING
# ════════════════════════════════════════════════════════

def engineer_features(df):
    """Adds all ML features to raw dataframe."""
    d = df.copy()

    d['hour_sin']  = np.sin(2 * np.pi * d.index.hour / 24)
    d['hour_cos']  = np.cos(2 * np.pi * d.index.hour / 24)
    d['dow_sin']   = np.sin(2 * np.pi * d.index.dayofweek / 7)
    d['dow_cos']   = np.cos(2 * np.pi * d.index.dayofweek / 7)
    d['month_sin'] = np.sin(2 * np.pi * d.index.month / 12)
    d['month_cos'] = np.cos(2 * np.pi * d.index.month / 12)
    d['quarter']   = d.index.quarter

    d['is_weekend']      = (d.index.dayofweek >= 5).astype(int)
    d['is_monsoon']      = d.index.month.isin([6,7,8,9]).astype(int)
    d['is_summer']       = d.index.month.isin([4,5,6]).astype(int)
    d['is_morning_peak'] = d.index.hour.isin(range(8,12)).astype(int)
    d['is_evening_peak'] = d.index.hour.isin(range(18,23)).astype(int)
    d['is_tod_cheap']    = d.index.hour.isin(range(10,16)).astype(int)
    d['is_night']        = d.index.hour.isin(list(range(0,6))).astype(int)

    for lag in [1,2,3,6,12,24,48,168]:
        d[f'load_lag_{lag}h'] = d['load_kw'].shift(lag)

    for w in [3,6,24]:
        d[f'load_roll_{w}h'] = d['load_kw'].rolling(w).mean()
    d['load_roll_std_24h'] = d['load_kw'].rolling(24).std()

    d['solar_lag_24h'] = d['solar_kw'].shift(24)
    rolling_solar_max  = d['solar_kw'].rolling(24).max().replace(0, 1)
    d['cloud_factor']  = (d['solar_kw'] / rolling_solar_max).clip(0, 1)
    d['temp_roll_6h']  = d['temp_c'].rolling(6).mean()

    d['peak_x_monsoon'] = d['is_evening_peak'] * d['is_monsoon']
    d['peak_x_summer']  = d['is_morning_peak'] * d['is_summer']

    return d.dropna()


# ════════════════════════════════════════════════════════
# MODEL TRAINING
# ════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def train_xgboost(df_raw):
    """
    Trains XGBoost on historical data.
    Walk-forward split — no data leakage.
    Cached — runs once per session.
    """
    df    = engineer_features(df_raw)
    split = int(len(df) * 0.82)

    X_train = df[FEATURES].iloc[:split]
    y_train = df['load_kw'].iloc[:split]
    X_test  = df[FEATURES].iloc[split:]
    y_test  = df['load_kw'].iloc[split:]

    model = xgb.XGBRegressor(
        n_estimators     = 700,
        max_depth        = 6,
        learning_rate    = 0.04,
        subsample        = 0.80,
        colsample_bytree = 0.80,
        min_child_weight = 3,
        reg_alpha        = 0.10,
        reg_lambda       = 1.00,
        random_state     = 42,
        verbosity        = 0,
    )
    model.fit(X_train, y_train)

    preds = np.clip(model.predict(X_test), 0, None)
    mae   = mean_absolute_error(y_test, preds)
    mape  = float(np.mean(np.abs((y_test - preds) / y_test.clip(1))) * 100)

    importance = pd.Series(
        model.feature_importances_, index=FEATURES
    ).sort_values(ascending=False)

    # Per-hour error for confidence bands
    err_by_hour = {}
    for h in range(24):
        mask = X_test.index.hour == h
        if mask.sum() > 0:
            err_by_hour[h] = float(np.abs(y_test[mask] - preds[mask]).mean())
        else:
            err_by_hour[h] = 25.0

    return model, mae, mape, importance, X_test, y_test, preds, err_by_hour


# ════════════════════════════════════════════════════════
# FORECAST ENGINE
# ════════════════════════════════════════════════════════

def generate_forecast(model, df_raw, err_by_hour,
                      solar_capacity_kw=200, horizon=24):
    """
    Generates horizon-hour ahead forecasts for:
    - Load (kW) with confidence bands
    - Solar (kW) using physics model
    - Battery SoC (%) simulation
    """
    df_feat      = engineer_features(df_raw)
    temp_history = df_feat.tail(400).copy()
    forecasts, uppers, lowers, solar_fc = [], [], [], []

    for step in range(horizon):
        next_ts = temp_history.index[-1] + pd.Timedelta(hours=1)
        h, m    = next_ts.hour, next_ts.month

        # Build minimal new row
        new_row = pd.DataFrame({
            'load_kw' : [temp_history['load_kw'].iloc[-1]],
            'solar_kw': [0.0],
            'temp_c'  : [temp_history['temp_c'].iloc[-1]],
        }, index=[next_ts])

        extended = pd.concat([temp_history, new_row])
        extended = engineer_features(extended)

        X_step = extended[FEATURES].iloc[-1:]
        pred   = float(np.clip(model.predict(X_step)[0], 80, 600))
        err    = err_by_hour.get(h, 25.0)

        forecasts.append(pred)
        uppers.append(pred + 1.6 * err)
        lowers.append(max(0.0, pred - 1.6 * err))

        # Solar physics
        if 6 <= h <= 18:
            angle = np.sin((h - 6) * np.pi / 12)
            s     = solar_capacity_kw * angle
            cloud = (0.40 if m in [6,7,8,9] else
                     0.85 if m in [12,1,2]  else 0.82)
            solar_fc.append(max(0.0, s * cloud))
        else:
            solar_fc.append(0.0)

        new_row['load_kw'] = pred
        temp_history       = pd.concat([temp_history, new_row])

    # Battery SoC simulation
    soc       = 72.0
    cap_kwh   = 500.0
    eta       = 0.95
    soc_trace = [soc]

    for load_v, solar_v in zip(forecasts, solar_fc):
        net       = solar_v - load_v
        d_soc     = (net * eta / cap_kwh) * 100
        soc       = float(np.clip(soc + d_soc, 10, 95))
        soc_trace.append(soc)

    idx = [
        df_raw.index[-1] + pd.Timedelta(hours=i + 1)
        for i in range(horizon)
    ]

    fc_df = pd.DataFrame({
        'forecast_kw' : forecasts,
        'upper_kw'    : uppers,
        'lower_kw'    : lowers,
        'solar_kw'    : solar_fc,
        'net_kw'      : [s - l for s, l in zip(solar_fc, forecasts)],
    }, index=idx)

    return fc_df, soc_trace


# ════════════════════════════════════════════════════════
# BRAIN — DECISIONS & ALERTS
# ════════════════════════════════════════════════════════

def run_brain(fc_df, soc_trace, current_soc,
              current_load, current_solar,
              current_hour, tariff):
    """
    Analyses forecasts and produces decisions + alerts.
    Returns list of (severity, message, tag) tuples.
    """
    alerts    = []
    decisions = []

    min_soc      = min(soc_trace)
    min_soc_step = soc_trace.index(min_soc)
    peak_load    = fc_df['forecast_kw'].max()
    peak_hr      = fc_df['forecast_kw'].idxmax().hour
    is_cheap     = current_hour in tariff['tod_cheap_hours']
    is_peak_rate = current_hour in tariff['tod_peak_hours']
    peak_coming  = any(
        h in tariff['tod_peak_hours']
        for h in range(current_hour, min(current_hour + 5, 24))
    )
    net_kw       = current_solar - current_load
    hours_left   = (
        (current_soc - 10) * 500 /
        max(1, abs(net_kw) * 100 / 95)
        if net_kw < 0 else 999
    )

    # Rule 1: Critical SoC right now
    if current_soc < 20:
        alerts.append((
            'CRITICAL',
            f'🔴 Battery at {current_soc:.0f}% — CRITICAL. '
            f'Import from grid immediately. '
            f'Estimated {hours_left:.1f}h before shutdown.',
            'EMERGENCY CHARGE'
        ))
        decisions.append('tag-critical')

    # Rule 2: Battery will drop critically in next 24h
    elif min_soc < 20:
        alerts.append((
            'WARNING',
            f'🟡 Battery forecast to reach {min_soc:.0f}% '
            f'in {min_soc_step}h. '
            f'Recommend grid charging before {min_soc_step - 1}:00.',
            'PLAN CHARGE'
        ))
        decisions.append('tag-charge')

    # Rule 3: Cheap tariff — good time to charge
    if is_cheap and current_soc < 75 and not is_peak_rate:
        rate_saved = tariff['peak_rate'] - tariff['cheap_rate']
        savings_hr = (75 - current_soc) / 100 * 500 * rate_saved
        alerts.append((
            'INFO',
            f'🔵 Cheap tariff active (₹{tariff["cheap_rate"]}/kWh). '
            f'Charging battery saves ₹{savings_hr:.0f} '
            f'vs importing during evening peak.',
            'CHARGE NOW'
        ))
        decisions.append('tag-charge')

    # Rule 4: Pre-charge before peak
    if peak_coming and current_soc < 65 and is_cheap:
        hrs_to_peak = next(
            (h for h in tariff['tod_peak_hours'] if h > current_hour),
            18
        ) - current_hour
        alerts.append((
            'WARNING',
            f'🟡 Evening peak tariff starts in {hrs_to_peak}h. '
            f'Battery at {current_soc:.0f}% — '
            f'pre-charge to 80% now at cheap rate.',
            'PRE-CHARGE'
        ))
        decisions.append('tag-charge')

    # Rule 5: Peak demand spike incoming
    if peak_load > 400:
        demand_cost = (peak_load - 400) * tariff['demand_charge_per_kw'] / 30
        alerts.append((
            'WARNING',
            f'🟡 Peak demand forecast: {peak_load:.0f} kW at {peak_hr}:00. '
            f'Battery dispatch will shave ~{peak_load - 400:.0f} kW, '
            f'saving ₹{demand_cost:.0f} in demand charges.',
            'DEMAND SHAVE'
        ))
        decisions.append('tag-shave')

    # Rule 6: Currently discharging at peak rate — good
    if is_peak_rate and current_soc > 30 and net_kw < 0:
        saving_hr = abs(net_kw) * (
            tariff['peak_rate'] - tariff['normal_rate']
        )
        alerts.append((
            'INFO',
            f'🔵 Peak rate active (₹{tariff["peak_rate"]}/kWh). '
            f'Battery covering {abs(net_kw):.0f} kW load — '
            f'saving ₹{saving_hr:.0f}/hr vs grid import.',
            'DISCHARGING'
        ))
        decisions.append('tag-shave')

    # All good
    if not alerts:
        alerts.append((
            'OK',
            f'🟢 All systems normal. Battery at {current_soc:.0f}%, '
            f'{hours_left:.0f}h reserve. '
            f'Solar covering {current_solar:.0f} kW of '
            f'{current_load:.0f} kW demand.',
            'HOLD'
        ))
        decisions.append('tag-hold')

    return alerts, decisions


# ════════════════════════════════════════════════════════
# LIVE WEATHER (open-meteo — free, no key needed)
# ════════════════════════════════════════════════════════

CITY_COORDS = {
    "Kolkata"  : (22.57, 88.36),
    "Mumbai"   : (19.07, 72.87),
    "Delhi"    : (28.61, 77.20),
    "Chennai"  : (13.08, 80.27),
    "Bangalore": (12.97, 77.59),
    "Hyderabad": (17.38, 78.47),
    "Ahmedabad": (23.02, 72.57),
    "Pune"     : (18.52, 73.86),
}

@st.cache_data(ttl=1800, show_spinner=False)
def get_live_weather(city="Kolkata"):
    """Fetches 7-day weather forecast from Open-Meteo (free)."""
    lat, lon = CITY_COORDS.get(city, (22.57, 88.36))
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude"    : lat,
                "longitude"   : lon,
                "hourly"      : "temperature_2m,cloudcover,direct_radiation,diffuse_radiation,precipitation_probability",
                "timezone"    : "Asia/Kolkata",
                "forecast_days": 7,
                "past_days"   : 2,
            },
            timeout=8
        )
        if r.status_code == 200:
            h = r.json()['hourly']
            df = pd.DataFrame({
                'temp_c'        : h['temperature_2m'],
                'cloud_pct'     : h['cloudcover'],
                'direct_rad'    : h['direct_radiation'],
                'diffuse_rad'   : h['diffuse_radiation'],
                'rain_prob_pct' : h['precipitation_probability'],
            }, index=pd.to_datetime(h['time']))
            return df
    except Exception:
        pass
    return None


# ════════════════════════════════════════════════════════
# CSV PARSER
# ════════════════════════════════════════════════════════

def parse_customer_csv(uploaded_file):
    """
    Auto-parses customer uploaded CSV from any inverter brand
    or energy meter. Handles Indian date formats.
    """
    try:
        try:
            df_raw = pd.read_csv(uploaded_file, encoding='utf-8')
        except Exception:
            uploaded_file.seek(0)
            df_raw = pd.read_csv(uploaded_file, encoding='latin-1')

        # Find timestamp column
        ts_col = None
        for col in df_raw.columns:
            try:
                parsed = pd.to_datetime(
                    df_raw[col], dayfirst=True, errors='coerce'
                )
                if parsed.notna().sum() > len(df_raw) * 0.7:
                    ts_col = col
                    break
            except Exception:
                continue

        if ts_col is None:
            st.error("No timestamp column found in CSV.")
            return None

        df_raw['_ts'] = pd.to_datetime(
            df_raw[ts_col], dayfirst=True, errors='coerce'
        )
        df_raw = df_raw.dropna(subset=['_ts'])
        df_raw = df_raw.set_index('_ts').sort_index()

        # Find load column
        load_keywords = ['load','demand','power','kw','kwh',
                         'consumption','energy','units']
        load_col = None
        for kw in load_keywords:
            for col in df_raw.columns:
                if kw in col.lower():
                    load_col = col
                    break
            if load_col:
                break

        if load_col is None:
            numeric = df_raw.select_dtypes(include=[np.number]).columns
            if len(numeric):
                load_col = numeric[0]

        df = pd.DataFrame(index=df_raw.index)
        df['load_kw'] = pd.to_numeric(df_raw[load_col], errors='coerce')

        # Convert W → kW if needed
        if df['load_kw'].median() > 5000:
            df['load_kw'] /= 1000

        # Find solar column
        solar_keywords = ['solar','pv','generation','gen',
                          'inverter','renewable']
        solar_col = None
        for kw in solar_keywords:
            for col in df_raw.columns:
                if kw in col.lower() and col != load_col:
                    solar_col = col
                    break
            if solar_col:
                break

        if solar_col:
            df['solar_kw'] = pd.to_numeric(
                df_raw[solar_col], errors='coerce'
            )
            if df['solar_kw'].median() > 5000:
                df['solar_kw'] /= 1000
        else:
            # Synthetic solar if none provided
            df['solar_kw'] = [
                max(0, 150 * np.sin((ts.hour-6)*np.pi/12)
                    * (0.4 if ts.month in [6,7,8,9] else 0.8))
                if 6 <= ts.hour <= 18 else 0.0
                for ts in df.index
            ]

        # Temperature
        df['temp_c'] = [
            28 + 8 * np.sin((ts.month - 4) * np.pi / 6)
            for ts in df.index
        ]

        df = df.dropna(subset=['load_kw'])
        df['load_kw']  = df['load_kw'].clip(0, 5000)
        df['solar_kw'] = df['solar_kw'].fillna(0).clip(0, 2000)

        # Resample to hourly
        df = df.resample('1h').mean().dropna(subset=['load_kw'])

        return df

    except Exception as e:
        st.error(f"Could not parse file: {e}")
        return None


# ════════════════════════════════════════════════════════
# PLOT HELPERS
# ════════════════════════════════════════════════════════

def styled_figure(height=320):
    """Returns a pre-styled plotly figure."""
    fig = go.Figure()
    fig.update_layout(
        height           = height,
        paper_bgcolor    = PLOT_COLORS['bg'],
        plot_bgcolor     = PLOT_COLORS['panel'],
        font             = dict(
            family='Inter, sans-serif',
            color='#64748b',
            size=12
        ),
        margin           = dict(t=40, b=20, l=10, r=10),
        hovermode        = 'x unified',
        legend           = dict(
            orientation='h',
            y=1.06,
            bgcolor='rgba(0,0,0,0)',
            font=dict(color='#94a3b8', size=11),
        ),
        xaxis=dict(
            gridcolor=PLOT_COLORS['grid_line'],
            showgrid=True,
            zeroline=False,
            tickfont=dict(color='#4a6fa5', size=11),
        ),
        yaxis=dict(
            gridcolor=PLOT_COLORS['grid_line'],
            showgrid=True,
            zeroline=False,
            tickfont=dict(color='#4a6fa5', size=11),
        ),
    )
    return fig


def add_threshold_line(fig, y, label, color, row=1):
    fig.add_hline(
        y=y, row=row, col=1,
        line=dict(color=color, width=1, dash='dot'),
        annotation=dict(
            text=label,
            font=dict(color=color, size=10),
            xanchor='right',
        )
    )


# ════════════════════════════════════════════════════════
# SAVINGS CALCULATOR
# ════════════════════════════════════════════════════════

def calculate_savings(fc_df, tariff, battery_kwh=500):
    """Calculates monthly and annual savings from AI management."""

    # ToD arbitrage — buy cheap, avoid peak
    cheap_hrs   = [i for i, ts in enumerate(fc_df.index)
                   if ts.hour in tariff['tod_cheap_hours']]
    peak_hrs    = [i for i, ts in enumerate(fc_df.index)
                   if ts.hour in tariff['tod_peak_hours']]

    cheap_energy = fc_df['forecast_kw'].iloc[cheap_hrs].sum()
    peak_energy  = fc_df['forecast_kw'].iloc[peak_hrs].sum()
    arbitrage    = min(cheap_energy, battery_kwh) * (
        tariff['peak_rate'] - tariff['cheap_rate']
    ) * 0.35

    # Demand charge reduction (15% peak shaving)
    peak_demand   = fc_df['forecast_kw'].max()
    demand_saving = peak_demand * 0.15 * tariff['demand_charge_per_kw'] / 30

    daily         = arbitrage + demand_saving
    monthly       = daily * 30
    annual        = monthly * 12

    return {
        'daily'            : daily,
        'monthly'          : monthly,
        'annual'           : annual,
        'arbitrage_daily'  : arbitrage,
        'demand_daily'     : demand_saving,
        'peak_demand_kw'   : peak_demand,
    }


# ════════════════════════════════════════════════════════
# ── SIDEBAR ──
# ════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown(
        '<div style="font-size:20px;font-weight:700;'
        'color:#e2e8f0;letter-spacing:-0.5px">⚡ MicroGrid AI</div>'
        '<div style="font-size:11px;color:#4a6fa5;'
        'letter-spacing:2px;text-transform:uppercase;'
        'margin-bottom:16px">Energy Intelligence</div>',
        unsafe_allow_html=True
    )
    st.divider()

    # ── Facility ──
    st.markdown(
        '<div style="font-size:10px;letter-spacing:2px;'
        'text-transform:uppercase;color:#1d4ed8;'
        'font-weight:600;margin-bottom:8px">Facility</div>',
        unsafe_allow_html=True
    )

    facility = st.selectbox(
        "Facility name",
        ["Apollo Multispeciality Hospital, Kolkata",
         "AMRI Hospital, Salt Lake",
         "Medica Superspecialty Hospital",
         "IIT Kharagpur Campus",
         "Jadavpur University Campus",
         "Custom Facility"],
        label_visibility="collapsed"
    )

    city = st.selectbox(
        "City",
        list(CITY_COORDS.keys()),
        label_visibility="visible"
    )

    tariff_name = st.selectbox(
        "State tariff",
        list(INDIA_TARIFFS.keys())
    )
    tariff = INDIA_TARIFFS[tariff_name]

    st.divider()

    # ── System specs ──
    st.markdown(
        '<div style="font-size:10px;letter-spacing:2px;'
        'text-transform:uppercase;color:#1d4ed8;'
        'font-weight:600;margin-bottom:8px">System</div>',
        unsafe_allow_html=True
    )

    battery_kwh  = st.slider("Battery (kWh)",  100, 2000, 500, 50)
    solar_cap_kw = st.slider("Solar (kW)",       50,  500, 200, 10)
    current_soc  = st.slider("Current SoC (%)",  10,  100,  68,  1)

    st.divider()

    # ── Data source ──
    st.markdown(
        '<div style="font-size:10px;letter-spacing:2px;'
        'text-transform:uppercase;color:#1d4ed8;'
        'font-weight:600;margin-bottom:8px">Data Source</div>',
        unsafe_allow_html=True
    )

    data_mode = st.radio(
        "Source",
        ["Demo (AI simulated)", "Upload CSV",
         "Live weather"],
        label_visibility="collapsed"
    )

    uploaded_file = None
    if data_mode == "Upload CSV":
        uploaded_file = st.file_uploader(
            "Upload inverter/meter CSV",
            type=['csv'],
            label_visibility="collapsed"
        )
        st.caption(
            "Accepts: Sungrow, Huawei, SolarEdge, "
            "Growatt, or any energy meter CSV"
        )

    st.divider()
    st.caption(
        f"Built with ❤️ in Kolkata\n"
        f"MicroGrid AI v1.0\n"
        f"© 2026 · All rights reserved"
    )


# ════════════════════════════════════════════════════════
# ── LOAD DATA ──
# ════════════════════════════════════════════════════════

data_tag = "demo"

if data_mode == "Upload CSV" and uploaded_file is not None:
    with st.spinner("Parsing your energy data..."):
        df_raw = parse_customer_csv(uploaded_file)
    if df_raw is None or len(df_raw) < 168:
        st.warning(
            "Need at least 1 week of hourly data. "
            "Using demo data instead."
        )
        df_raw = generate_hospital_data(
            n_days=365, solar_kw=solar_cap_kw
        )
    else:
        data_tag = "real"
        st.success(
            f"✓ Real data loaded — "
            f"{len(df_raw)} hours "
            f"({df_raw.index[0].strftime('%d %b %Y')} → "
            f"{df_raw.index[-1].strftime('%d %b %Y')})"
        )

elif data_mode == "Live weather":
    with st.spinner(f"Loading live weather for {city}..."):
        weather_df = get_live_weather(city)
    df_raw = generate_hospital_data(n_days=365, solar_kw=solar_cap_kw)

    if weather_df is not None:
        # Blend real weather into synthetic dataset
        recent = df_raw.index[df_raw.index >= weather_df.index[0]]
        if len(recent):
            df_raw.loc[recent, 'temp_c'] = (
                weather_df['temp_c']
                .reindex(recent, method='nearest')
                .values
            )
            total_rad = (
                weather_df['direct_rad'] + weather_df['diffuse_rad']
            )
            df_raw.loc[recent, 'solar_kw'] = (
                (total_rad / 1000 * solar_cap_kw * 0.20 * 0.86)
                .clip(lower=0)
                .reindex(recent, method='nearest')
                .values
            )
        data_tag = "weather"
    else:
        st.warning("Weather API unavailable. Using demo data.")

else:
    df_raw = generate_hospital_data(n_days=365, solar_kw=solar_cap_kw)


# ════════════════════════════════════════════════════════
# ── TRAIN MODEL ──
# ════════════════════════════════════════════════════════

with st.spinner("Training XGBoost forecast model..."):
    (model, mae, mape,
     importance, X_test,
     y_test, test_preds,
     err_by_hour) = train_xgboost(df_raw)

# ── GENERATE FORECAST ──
with st.spinner("Generating 24-hour AI forecast..."):
    fc_df, soc_trace = generate_forecast(
        model, df_raw, err_by_hour,
        solar_capacity_kw=solar_cap_kw
    )

# ── CURRENT VALUES ──
current = df_raw.iloc[-1]
current_load  = float(current['load_kw'])
current_solar = float(current['solar_kw'])
current_hour  = pd.Timestamp.now().hour
net_now       = current_solar - current_load

# ── RUN BRAIN ──
alerts, decision_tags = run_brain(
    fc_df, soc_trace,
    current_soc, current_load, current_solar,
    current_hour, tariff
)

# ── SAVINGS ──
savings = calculate_savings(fc_df, tariff, battery_kwh)


# ════════════════════════════════════════════════════════
# ── HEADER ──
# ════════════════════════════════════════════════════════

col_title, col_badge = st.columns([4, 1])

with col_title:
    st.markdown(
        f'<div class="page-title">{facility}</div>'
        f'<div class="page-subtitle">'
        f'{city} · {tariff_name} · '
        f'{pd.Timestamp.now().strftime("%d %b %Y, %I:%M %p")}'
        f'</div>',
        unsafe_allow_html=True
    )

with col_badge:
    source_label = {
        "demo"   : "🔬 Demo mode",
        "real"   : "📡 Real data",
        "weather": "🌤 Live weather",
    }.get(data_tag, "Demo")
    st.markdown(
        f'<div style="margin-top:12px">'
        f'<div class="live-badge">'
        f'<div class="live-dot"></div>{source_label}'
        f'</div></div>',
        unsafe_allow_html=True
    )


# ════════════════════════════════════════════════════════
# ── METRIC ROW ──
# ════════════════════════════════════════════════════════

m1, m2, m3, m4, m5, m6 = st.columns(6)

m1.metric(
    "Battery SoC",
    f"{current_soc}%",
    f"{'↓ Draining' if net_now < 0 else '↑ Charging'}"
)
m2.metric("Load Now",    f"{current_load:.0f} kW")
m3.metric("Solar Now",   f"{current_solar:.0f} kW")
m4.metric(
    "AI Accuracy",
    f"{max(0, 100-mape):.1f}%",
    f"MAE {mae:.0f} kW"
)
m5.metric(
    "24h Peak",
    f"{fc_df['forecast_kw'].max():.0f} kW",
    f"at {fc_df['forecast_kw'].idxmax().strftime('%H:%M')}"
)
m6.metric(
    "Min SoC (24h)",
    f"{min(soc_trace):.0f}%",
    delta=(
        "⚠ Low" if min(soc_trace) < 25 else "✓ Safe"
    ),
    delta_color="inverse" if min(soc_trace) < 25 else "normal"
)


# ════════════════════════════════════════════════════════
# ── BRAIN ALERTS ──
# ════════════════════════════════════════════════════════

st.markdown(
    '<div class="section-label">Brain Decisions</div>',
    unsafe_allow_html=True
)

# Decision tags row
tags_html = "".join([
    f'<span class="decision-tag {tag}">'
    f'{alerts[i][2]}</span>'
    for i, tag in enumerate(decision_tags)
])
st.markdown(tags_html, unsafe_allow_html=True)
st.markdown("<div style='margin:8px 0'></div>",
            unsafe_allow_html=True)

# Alert messages
for severity, message, _ in alerts:
    css = {
        'CRITICAL': 'alert-critical',
        'WARNING' : 'alert-warning',
        'INFO'    : 'alert-info',
        'OK'      : 'alert-ok',
    }.get(severity, 'alert-info')
    st.markdown(
        f'<div class="{css}">{message}</div>',
        unsafe_allow_html=True
    )


# ════════════════════════════════════════════════════════
# ── CHART 1: POWER BALANCE (last 7 days) ──
# ════════════════════════════════════════════════════════

st.markdown(
    '<div class="section-label">Power Balance — Last 7 Days</div>',
    unsafe_allow_html=True
)

df_week = df_raw.tail(7 * 24)
fig1    = styled_figure(300)

fig1.add_trace(go.Scatter(
    x=df_week.index,
    y=df_week['load_kw'],
    name='Load (kW)',
    line=dict(color=PLOT_COLORS['load'], width=1.5),
    hovertemplate='%{y:.0f} kW<extra>Load</extra>',
))
fig1.add_trace(go.Scatter(
    x=df_week.index,
    y=df_week['solar_kw'],
    name='Solar (kW)',
    line=dict(color=PLOT_COLORS['solar'], width=1.5),
    fill='tozeroy',
    fillcolor='rgba(245,158,11,0.07)',
    hovertemplate='%{y:.0f} kW<extra>Solar</extra>',
))
# Peak demand zone
fig1.add_hrect(
    y0=420, y1=600,
    fillcolor='rgba(239,68,68,0.04)',
    line_width=0,
    annotation_text="Demand charge zone",
    annotation_font=dict(color='#ef4444', size=10),
    annotation_position="top right",
)
# Net area
net_series = df_week['solar_kw'] - df_week['load_kw']
fig1.add_trace(go.Scatter(
    x=df_week.index,
    y=net_series.clip(lower=0),
    name='Solar surplus',
    line=dict(width=0),
    fill='tozeroy',
    fillcolor='rgba(16,185,129,0.05)',
    showlegend=False,
))

fig1.update_layout(
    title=dict(
        text='', x=0
    )
)
st.plotly_chart(fig1, use_container_width=True)


# ════════════════════════════════════════════════════════
# ── CHART 2: 24H AI FORECAST ──
# ════════════════════════════════════════════════════════

st.markdown(
    '<div class="section-label">AI Forecast — Next 24 Hours</div>',
    unsafe_allow_html=True
)

fig2 = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.06,
    row_heights=[0.62, 0.38],
)

# Confidence band
fig2.add_trace(go.Scatter(
    x=list(fc_df.index) + list(fc_df.index[::-1]),
    y=list(fc_df['upper_kw']) + list(fc_df['lower_kw'][::-1]),
    fill='toself',
    fillcolor='rgba(59,130,246,0.07)',
    line=dict(color='rgba(0,0,0,0)'),
    name='Confidence band',
    hoverinfo='skip',
), row=1, col=1)

# Forecast line
fig2.add_trace(go.Scatter(
    x=fc_df.index,
    y=fc_df['forecast_kw'],
    name='AI Load Forecast',
    line=dict(color=PLOT_COLORS['forecast'], width=2.5),
    hovertemplate='%{y:.0f} kW<extra>Forecast</extra>',
), row=1, col=1)

# Solar forecast
fig2.add_trace(go.Scatter(
    x=fc_df.index,
    y=fc_df['solar_kw'],
    name='Solar Forecast',
    line=dict(color=PLOT_COLORS['solar'], width=1.5, dash='dot'),
    hovertemplate='%{y:.0f} kW<extra>Solar</extra>',
), row=1, col=1)

# Demand limit
fig2.add_hline(
    y=420, row=1, col=1,
    line=dict(color='rgba(239,68,68,0.5)', width=1, dash='dash'),
    annotation=dict(
        text="Demand limit 420 kW",
        font=dict(color='#ef4444', size=10),
        xanchor='right',
    )
)

# SoC colour-coded
soc_vals   = soc_trace[1:]
soc_colors = [
    '#ef4444' if s < 20 else
    '#f59e0b' if s < 35 else
    '#10b981'
    for s in soc_vals
]
fig2.add_trace(go.Scatter(
    x=fc_df.index,
    y=soc_vals,
    name='Battery SoC',
    line=dict(color=PLOT_COLORS['soc'], width=2.5),
    fill='tozeroy',
    fillcolor='rgba(16,185,129,0.06)',
    hovertemplate='%{y:.1f}%<extra>Battery SoC</extra>',
), row=2, col=1)

# SoC thresholds
for thresh, col, lbl in [
    (20, 'rgba(239,68,68,0.7)', 'Critical 20%'),
    (35, 'rgba(245,158,11,0.6)', 'Warning 35%'),
]:
    fig2.add_hline(
        y=thresh, row=2, col=1,
        line=dict(color=col, width=1, dash='dot'),
        annotation=dict(
            text=lbl,
            font=dict(color=col, size=10),
            xanchor='right',
        )
    )

# Style
fig2.update_layout(
    height=460,
    paper_bgcolor=PLOT_COLORS['bg'],
    plot_bgcolor=PLOT_COLORS['panel'],
    font=dict(family='Inter', color='#64748b', size=12),
    margin=dict(t=20, b=20, l=10, r=10),
    hovermode='x unified',
    legend=dict(
        orientation='h', y=1.04,
        bgcolor='rgba(0,0,0,0)',
        font=dict(color='#94a3b8', size=11),
    ),
)
fig2.update_xaxes(gridcolor=PLOT_COLORS['grid_line'], zeroline=False)
fig2.update_yaxes(gridcolor=PLOT_COLORS['grid_line'], zeroline=False)
fig2.update_yaxes(
    title_text='kW', row=1, col=1,
    title_font=dict(color='#4a6fa5', size=11)
)
fig2.update_yaxes(
    title_text='SoC %', row=2, col=1,
    range=[0, 100],
    title_font=dict(color='#4a6fa5', size=11)
)

st.plotly_chart(fig2, use_container_width=True)


# ════════════════════════════════════════════════════════
# ── CHART 3: BACKTEST + FEATURE IMPORTANCE ──
# ════════════════════════════════════════════════════════

st.markdown(
    '<div class="section-label">Model Performance</div>',
    unsafe_allow_html=True
)

col_bt, col_fi = st.columns([3, 2])

with col_bt:
    hrs  = min(168, len(y_test))
    fig3 = styled_figure(260)
    fig3.add_trace(go.Scatter(
        y=y_test.values[:hrs],
        name='Actual',
        line=dict(color=PLOT_COLORS['load'], width=1.5),
    ))
    fig3.add_trace(go.Scatter(
        y=test_preds[:hrs],
        name='AI Predicted',
        line=dict(color=PLOT_COLORS['forecast'],
                  width=1.5, dash='dot'),
    ))
    fig3.update_layout(
        title=dict(
            text='Backtest — Actual vs AI Predicted (1 Week)',
            font=dict(color='#94a3b8', size=12),
            x=0.01,
        )
    )
    st.plotly_chart(fig3, use_container_width=True)

with col_fi:
    st.markdown(
        '<div style="font-size:12px;color:#4a6fa5;'
        'margin:8px 0 12px;font-weight:500">'
        'Top predictive features</div>',
        unsafe_allow_html=True
    )
    top5 = importance.head(5)
    max_imp = float(top5.iloc[0])
    for feat, score in top5.items():
        label = (feat
                 .replace('load_', '')
                 .replace('_h', 'h')
                 .replace('_', ' ')
                 .title())
        pct = score / max_imp * 100
        bar_color = (
            '#3b82f6' if 'lag' in feat else
            '#10b981' if 'roll' in feat else
            '#f59e0b'
        )
        st.markdown(
            f'<div style="margin-bottom:10px">'
            f'<div style="display:flex;justify-content:space-between;'
            f'font-size:11px;color:#94a3b8;margin-bottom:4px">'
            f'<span>{label}</span>'
            f'<span style="color:#e2e8f0;font-weight:500">'
            f'{score:.3f}</span></div>'
            f'<div style="height:4px;background:#1e2d45;'
            f'border-radius:2px;overflow:hidden">'
            f'<div style="width:{pct:.0f}%;height:100%;'
            f'background:{bar_color};border-radius:2px;'
            f'transition:width 0.5s"></div>'
            f'</div></div>',
            unsafe_allow_html=True
        )

    st.markdown(
        f'<div class="accuracy-badge">'
        f'<span>MAE</span>'
        f'<span style="color:#e2e8f0;font-weight:600">'
        f'{mae:.1f} kW</span>'
        f'</div>'
        f'<div class="accuracy-badge">'
        f'<span>MAPE</span>'
        f'<span style="color:#e2e8f0;font-weight:600">'
        f'{mape:.1f}%</span>'
        f'</div>'
        f'<div class="accuracy-badge">'
        f'<span>Accuracy</span>'
        f'<span style="color:#10b981;font-weight:600">'
        f'{max(0, 100-mape):.1f}%</span>'
        f'</div>',
        unsafe_allow_html=True
    )


# ════════════════════════════════════════════════════════
# ── SAVINGS CALCULATOR ──
# ════════════════════════════════════════════════════════

st.markdown(
    '<div class="section-label">India Tariff Savings</div>',
    unsafe_allow_html=True
)

col_s1, col_s2, col_s3, col_s4 = st.columns(4)

with col_s1:
    st.markdown(
        f'<div class="savings-card">'
        f'<div class="savings-amount">'
        f'₹{savings["daily"]:,.0f}</div>'
        f'<div class="savings-label">Daily saving</div>'
        f'</div>',
        unsafe_allow_html=True
    )
with col_s2:
    st.markdown(
        f'<div class="savings-card">'
        f'<div class="savings-amount">'
        f'₹{savings["monthly"]/1000:.1f}K</div>'
        f'<div class="savings-label">Monthly saving</div>'
        f'</div>',
        unsafe_allow_html=True
    )
with col_s3:
    st.markdown(
        f'<div class="savings-card">'
        f'<div class="savings-amount">'
        f'₹{savings["annual"]/100000:.1f}L</div>'
        f'<div class="savings-label">Annual saving</div>'
        f'</div>',
        unsafe_allow_html=True
    )
with col_s4:
    payback = 40000 / max(1, savings['monthly'])
    st.markdown(
        f'<div class="savings-card">'
        f'<div class="savings-amount">'
        f'{payback:.1f}mo</div>'
        f'<div class="savings-label">Payback period</div>'
        f'</div>',
        unsafe_allow_html=True
    )

st.markdown(
    f'<div style="font-size:11px;color:#4a6fa5;'
    f'margin-top:10px;text-align:center">'
    f'Based on {tariff_name} — '
    f'₹{tariff["cheap_rate"]}/kWh cheap · '
    f'₹{tariff["normal_rate"]}/kWh normal · '
    f'₹{tariff["peak_rate"]}/kWh peak · '
    f'₹{tariff["demand_charge_per_kw"]}/kW demand charge · '
    f'Your fee: ₹40,000/month'
    f'</div>',
    unsafe_allow_html=True
)


# ════════════════════════════════════════════════════════
# ── TARIFF BREAKDOWN CHART ──
# ════════════════════════════════════════════════════════

st.markdown(
    '<div class="section-label">Tariff Rate — Next 24 Hours</div>',
    unsafe_allow_html=True
)

tariff_rates = [
    tariff['cheap_rate']  if h in tariff['tod_cheap_hours'] else
    tariff['peak_rate']   if h in tariff['tod_peak_hours']  else
    tariff['normal_rate']
    for h in range(24)
]
tariff_colors = [
    '#10b981' if h in tariff['tod_cheap_hours'] else
    '#ef4444' if h in tariff['tod_peak_hours']  else
    '#3b82f6'
    for h in range(24)
]

fig4 = styled_figure(200)
fig4.add_trace(go.Bar(
    x=list(range(24)),
    y=tariff_rates,
    marker_color=tariff_colors,
    name='Rate ₹/kWh',
    hovertemplate='Hour %{x}:00 — ₹%{y}/kWh<extra></extra>',
))
fig4.add_vline(
    x=current_hour,
    line=dict(color='white', width=1.5, dash='dash'),
    annotation=dict(
        text='Now',
        font=dict(color='white', size=11),
    )
)
fig4.update_layout(
    title=dict(
        text='🟢 Cheap  🔵 Normal  🔴 Peak',
        font=dict(color='#64748b', size=11),
        x=0.5, xanchor='center',
    ),
    showlegend=False,
    xaxis=dict(
        tickmode='array',
        tickvals=list(range(0, 24, 2)),
        ticktext=[f'{h:02d}:00' for h in range(0, 24, 2)],
    ),
    yaxis=dict(title='₹/kWh'),
)
st.plotly_chart(fig4, use_container_width=True)


# ════════════════════════════════════════════════════════
# ── FOOTER ──
# ════════════════════════════════════════════════════════

st.markdown(
    f'<div style="margin-top:40px;padding:20px;'
    f'border-top:1px solid #1e2d45;'
    f'display:flex;justify-content:space-between;'
    f'align-items:center;flex-wrap:wrap;gap:8px">'
    f'<div style="font-size:11px;color:#2d3d55">'
    f'MicroGrid AI · India-native energy intelligence · '
    f'Built for the mid-market</div>'
    f'<div style="font-size:11px;color:#2d3d55">'
    f'XGBoost v{xgb.__version__} · '
    f'Model trained on {len(df_raw)} hours · '
    f'{pd.Timestamp.now().strftime("%d %b %Y")}'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True
)
