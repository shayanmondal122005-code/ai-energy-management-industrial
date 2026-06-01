# dashboard.py
# MicroGrid AI  Complete Production Dashboard
# Integrates: XGBoost forecasting, Render backend, solar health,
# India tariff engine, battery SoC, brain decisions, WhatsApp alerts
# Deploy: Streamlit Cloud  push only this file + requirements.txt

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import xgboost as xgb
from sklearn.metrics import mean_absolute_error
import requests
import warnings
warnings.filterwarnings("ignore")

# 
# PAGE CONFIG
# 

st.set_page_config(
    page_title="MicroGrid AI",
    page_icon=":zap:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 
# STYLING  dark industrial theme with electric accents
# 

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap');

html, body, [class*="css"] { font-family: 'Syne', sans-serif; }

.stApp { background: #060a12; }
#MainMenu, footer, header { visibility: hidden; }

/* Metric cards */
div[data-testid="metric-container"] {
    background: #0b1120;
    border: 1px solid #1c2d47;
    border-radius: 10px;
    padding: 18px 16px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s;
}
div[data-testid="metric-container"]:hover { border-color: #2563eb; }
div[data-testid="metric-container"]::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #2563eb 0%, #10b981 100%);
}
div[data-testid="metric-container"] label {
    color: #3d5a80 !important;
    font-size: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    font-family: 'JetBrains Mono', monospace !important;
}
div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
    color: #e8eef7 !important;
    font-size: 24px !important;
    font-weight: 700 !important;
    font-family: 'Syne', sans-serif !important;
}
div[data-testid="stMetricDelta"] { font-size: 11px !important; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #080d18;
    border-right: 1px solid #1c2d47;
}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stSlider label,
section[data-testid="stSidebar"] .stRadio label { color: #4a6fa5 !important; }

/* Inputs */
.stSelectbox > div > div { background: #0b1120 !important; border-color: #1c2d47 !important; }
.stSlider > div > div > div { background: #2563eb !important; }

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    color: #fff;
    border: none;
    border-radius: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 1px;
    width: 100%;
    padding: 10px 16px;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(37,99,235,0.3);
}

hr { border-color: #1c2d47 !important; margin: 1.25rem 0 !important; }
h1,h2,h3 { color: #e8eef7 !important; }

/* Alert classes */
.a-critical {
    background: rgba(239,68,68,0.07);
    border: 1px solid rgba(239,68,68,0.25);
    border-left: 3px solid #ef4444;
    border-radius: 8px;
    padding: 12px 16px;
    color: #fca5a5;
    font-size: 13px;
    margin: 5px 0;
    font-family: 'Syne', sans-serif;
    line-height: 1.6;
}
.a-warning {
    background: rgba(245,158,11,0.07);
    border: 1px solid rgba(245,158,11,0.25);
    border-left: 3px solid #f59e0b;
    border-radius: 8px;
    padding: 12px 16px;
    color: #fcd34d;
    font-size: 13px;
    margin: 5px 0;
    line-height: 1.6;
}
.a-info {
    background: rgba(37,99,235,0.07);
    border: 1px solid rgba(37,99,235,0.25);
    border-left: 3px solid #2563eb;
    border-radius: 8px;
    padding: 12px 16px;
    color: #93c5fd;
    font-size: 13px;
    margin: 5px 0;
    line-height: 1.6;
}
.a-ok {
    background: rgba(16,185,129,0.07);
    border: 1px solid rgba(16,185,129,0.25);
    border-left: 3px solid #10b981;
    border-radius: 8px;
    padding: 12px 16px;
    color: #6ee7b7;
    font-size: 13px;
    margin: 5px 0;
    line-height: 1.6;
}
.a-solar {
    background: rgba(251,191,36,0.07);
    border: 1px solid rgba(251,191,36,0.25);
    border-left: 3px solid #fbbf24;
    border-radius: 8px;
    padding: 12px 16px;
    color: #fde68a;
    font-size: 13px;
    margin: 5px 0;
    line-height: 1.6;
}

/* Section headers */
.sec-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: #2563eb;
    font-weight: 600;
    padding-bottom: 10px;
    border-bottom: 1px solid #1c2d47;
    margin: 28px 0 16px;
}

/* Page title block */
.pg-title { font-size: 26px; font-weight: 800; color: #e8eef7; letter-spacing: -0.5px; line-height: 1.2; }
.pg-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #3d5a80;
    margin: 6px 0 0;
    letter-spacing: 0.5px;
}

/* Live dot */
.live-dot {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: rgba(16,185,129,0.1);
    border: 1px solid rgba(16,185,129,0.3);
    border-radius: 100px;
    padding: 4px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #10b981;
    font-weight: 500;
}
.pulse {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #10b981;
    animation: blink 2s infinite;
    flex-shrink: 0;
}
@keyframes blink {
    0%,100% { opacity:1; }
    50%      { opacity:0.2; }
}

/* Decision tags */
.dtag {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 100px;
    margin: 2px;
}
.dt-blue  { background: rgba(37,99,235,0.12); color:#60a5fa; border:1px solid rgba(37,99,235,0.3); }
.dt-green { background: rgba(16,185,129,0.12); color:#34d399; border:1px solid rgba(16,185,129,0.3); }
.dt-amber { background: rgba(245,158,11,0.12); color:#fbbf24; border:1px solid rgba(245,158,11,0.3); }
.dt-red   { background: rgba(239,68,68,0.15);  color:#f87171; border:1px solid rgba(239,68,68,0.3); }

/* Savings cards */
.sav-card {
    background: linear-gradient(135deg, #0b1a30 0%, #081020 100%);
    border: 1px solid #1c3a5e;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}
.sav-val { font-size: 30px; font-weight: 800; color: #10b981; letter-spacing: -1px; }
.sav-lab {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #3d5a80;
    margin-top: 6px;
}

/* Feature importance bars */
.fi-row { margin-bottom: 10px; }
.fi-label { display:flex; justify-content:space-between; font-size:11px; color:#4a6fa5; margin-bottom:4px; font-family:'JetBrains Mono',monospace; }
.fi-track { height:4px; background:#1c2d47; border-radius:2px; overflow:hidden; }
.fi-fill  { height:100%; border-radius:2px; transition:width 0.6s ease; }

/* Sidebar section label */
.sb-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #2563eb;
    font-weight: 600;
    margin: 16px 0 8px;
}
</style>
""", unsafe_allow_html=True)


# 
# CONSTANTS
# 

BACKEND_URL = "https://ai-energy-managementat12.onrender.com"

INDIA_TARIFFS = {
    "West Bengal  CESC": {
        "cheap": 4.20, "normal": 6.10, "peak": 7.85,
        "demand_per_kw": 320,
        "cheap_hours": list(range(10, 16)),
        "peak_hours" : list(range(18, 23)),
    },
    "Maharashtra  MSEDCL": {
        "cheap": 3.80, "normal": 5.90, "peak": 8.20,
        "demand_per_kw": 280,
        "cheap_hours": list(range(10, 16)),
        "peak_hours" : list(range(18, 22)),
    },
    "Tamil Nadu  TANGEDCO": {
        "cheap": 4.50, "normal": 6.40, "peak": 8.10,
        "demand_per_kw": 350,
        "cheap_hours": list(range(10, 17)),
        "peak_hours" : list(range(18, 23)),
    },
    "Karnataka  BESCOM": {
        "cheap": 4.10, "normal": 6.00, "peak": 7.70,
        "demand_per_kw": 295,
        "cheap_hours": list(range(10, 16)),
        "peak_hours" : list(range(18, 22)),
    },
    "Delhi  BSES/TPDDL": {
        "cheap": 3.90, "normal": 5.80, "peak": 7.50,
        "demand_per_kw": 260,
        "cheap_hours": list(range(10, 16)),
        "peak_hours" : list(range(17, 22)),
    },
}

CITIES = {
    "Kolkata"  : (22.57, 88.36),
    "Mumbai"   : (19.07, 72.87),
    "Delhi"    : (28.61, 77.20),
    "Chennai"  : (13.08, 80.27),
    "Bangalore": (12.97, 77.59),
    "Hyderabad": (17.38, 78.47),
    "Pune"     : (18.52, 73.86),
    "Ahmedabad": (23.02, 72.57),
}

COLORS = {
    "load"   : "#ef4444",
    "solar"  : "#f59e0b",
    "fc"     : "#3b82f6",
    "soc"    : "#10b981",
    "grid"   : "#8b5cf6",
    "conf"   : "rgba(59,130,246,0.07)",
    "gl"     : "#111d2e",
    "bg"     : "#060a12",
    "panel"  : "#0b1120",
}

FEATURES = [
    "hour_sin","hour_cos","dow_sin","dow_cos",
    "month_sin","month_cos","quarter",
    "is_weekend","is_monsoon","is_summer",
    "is_morning_peak","is_evening_peak",
    "is_tod_cheap","is_night",
    "load_lag_1h","load_lag_2h","load_lag_3h",
    "load_lag_6h","load_lag_12h",
    "load_lag_24h","load_lag_48h","load_lag_168h",
    "load_roll_3h","load_roll_6h",
    "load_roll_24h","load_roll_std_24h",
    "solar_lag_24h","cloud_factor",
    "temp_c","temp_roll_6h",
    "peak_x_monsoon","peak_x_summer",
]

MIN_HISTORY_HOURS = 48
MIN_MODEL_ROWS = 48


# 
# DATA  synthetic fallback
# 

@st.cache_data(show_spinner=False)
def synthetic_data(n_days=365, solar_kw=200, avg_kw=300, seed=42):
    np.random.seed(seed)
    hours = pd.date_range(
        pd.Timestamp.now() - pd.Timedelta(days=n_days),
        periods=n_days * 24, freq="1h"
    )
    load, solar, temp = [], [], []
    for ts in hours:
        h, m, dow = ts.hour, ts.month, ts.dayofweek
        f = (1.38 if 8<=h<=11 else 1.25 if 18<=h<=22
             else 0.72 if h<=5 else 1.0)
        if m in [4,5,6]: f *= 1.16
        if m in [7,8,9]: f *= 1.10
        if dow >= 5:     f *= 0.90
        load.append(float(np.clip(avg_kw*f + np.random.normal(0,18), avg_kw*0.5, avg_kw*1.6)))
        if 6 <= h <= 18:
            ang = np.sin((h-6)*np.pi/12)
            s   = solar_kw * ang
            s  *= float(np.random.beta(1.5,5) if m in [6,7,8,9]
                        else np.random.beta(8,2))
            solar.append(max(0.0, s + np.random.normal(0,8)))
        else:
            solar.append(0.0)
        temp.append(28 + 8*np.sin((m-4)*np.pi/6) + np.random.normal(0,1.5))
    return pd.DataFrame({"load_kw":load,"solar_kw":solar,"temp_c":temp}, index=hours)


# 
# DATA  Render backend
# 

@st.cache_data(ttl=300, show_spinner=False)
def fetch_backend(hours=500):
    try:
        r = requests.get(
            f"{BACKEND_URL}/history/csv",
            params={"hours": hours},
            timeout=35
        )
        if r.status_code == 200:
            from io import StringIO
            df = pd.read_csv(StringIO(r.text),
                             parse_dates=["timestamp"],
                             index_col="timestamp")
            if len(df) >= MIN_MODEL_ROWS:
                return df, "live", None
            return None, None, f"Backend returned only {len(df)} hourly rows (need {MIN_MODEL_ROWS}). POST /simulate/seed to populate."
        return None, None, f"Backend HTTP {r.status_code}"
    except requests.exceptions.ConnectionError:
        return None, None, f"Cannot reach {BACKEND_URL} — backend may be sleeping (Render free tier). Retrying..."
    except requests.exceptions.Timeout:
        return None, None, f"Backend timed out after 35s — Render is waking up. Refresh in 30s."
    except Exception as e:
        return None, None, str(e)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live():
    try:
        r = requests.get(f"{BACKEND_URL}/live", timeout=35)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_health():
    try:
        r = requests.get(f"{BACKEND_URL}/solar/health", timeout=35)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


@st.cache_data(ttl=120, show_spinner=False)
def fetch_stats():
    try:
        r = requests.get(f"{BACKEND_URL}/stats", timeout=35)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# 
# DATA  CSV upload parser
# 

def parse_csv(uploaded):
    try:
        try:
            raw = pd.read_csv(uploaded, encoding="utf-8")
        except Exception:
            uploaded.seek(0)
            raw = pd.read_csv(uploaded, encoding="latin-1")

        # Find timestamp col
        ts_col = None
        for col in raw.columns:
            try:
                p = pd.to_datetime(raw[col], dayfirst=True, errors="coerce")
                if p.notna().sum() > len(raw)*0.7:
                    ts_col = col; break
            except Exception:
                pass
        if ts_col is None:
            st.error("No timestamp column found."); return None

        raw["_ts"] = pd.to_datetime(raw[ts_col], dayfirst=True, errors="coerce")
        raw = raw.dropna(subset=["_ts"]).set_index("_ts").sort_index()

        # Load col
        lkw = ["load","demand","power","kw","kwh","consumption","units","energy"]
        load_col = next((c for kw in lkw for c in raw.columns if kw in c.lower()), None)
        if load_col is None:
            num = raw.select_dtypes(include=[np.number]).columns
            load_col = num[0] if len(num) else None
        if load_col is None:
            st.error("No load column found."); return None

        df = pd.DataFrame(index=raw.index)
        df["load_kw"] = pd.to_numeric(raw[load_col], errors="coerce")
        if df["load_kw"].median() > 5000:
            df["load_kw"] /= 1000

        # Solar col
        skw = ["solar","pv","generation","gen","inverter","renewable"]
        solar_col = next((c for kw in skw for c in raw.columns
                          if kw in c.lower() and c != load_col), None)
        if solar_col:
            df["solar_kw"] = pd.to_numeric(raw[solar_col], errors="coerce")
            if df["solar_kw"].median() > 5000:
                df["solar_kw"] /= 1000
        else:
            df["solar_kw"] = [
                max(0, 150*np.sin((ts.hour-6)*np.pi/12)
                    *(0.4 if ts.month in [6,7,8,9] else 0.8))
                if 6<=ts.hour<=18 else 0.0
                for ts in df.index
            ]

        df["temp_c"] = [28+8*np.sin((ts.month-4)*np.pi/6) for ts in df.index]
        df = df.dropna(subset=["load_kw"])
        df["load_kw"]  = df["load_kw"].clip(0, 5000)
        df["solar_kw"] = df["solar_kw"].fillna(0).clip(0, 2000)
        df = df.resample("1h").mean().dropna(subset=["load_kw"])

        st.sidebar.success(
            f"{len(df)} hours loaded\n"
            f"{df.index[0].strftime('%d %b %Y')} -> "
            f"{df.index[-1].strftime('%d %b %Y')}"
        )
        return df
    except Exception as e:
        st.error(f"Parse error: {e}"); return None


# 
# FEATURE ENGINEERING
# 

def engineer(df):
    d = df.copy()
    d["hour_sin"]  = np.sin(2*np.pi*d.index.hour/24)
    d["hour_cos"]  = np.cos(2*np.pi*d.index.hour/24)
    d["dow_sin"]   = np.sin(2*np.pi*d.index.dayofweek/7)
    d["dow_cos"]   = np.cos(2*np.pi*d.index.dayofweek/7)
    d["month_sin"] = np.sin(2*np.pi*d.index.month/12)
    d["month_cos"] = np.cos(2*np.pi*d.index.month/12)
    d["quarter"]   = d.index.quarter
    d["is_weekend"]      = (d.index.dayofweek>=5).astype(int)
    d["is_monsoon"]      = d.index.month.isin([6,7,8,9]).astype(int)
    d["is_summer"]       = d.index.month.isin([4,5,6]).astype(int)
    d["is_morning_peak"] = d.index.hour.isin(range(8,12)).astype(int)
    d["is_evening_peak"] = d.index.hour.isin(range(18,23)).astype(int)
    d["is_tod_cheap"]    = d.index.hour.isin(range(10,16)).astype(int)
    d["is_night"]        = d.index.hour.isin(list(range(0,6))).astype(int)
    for lag in [1,2,3,6,12,24,48,168]:
        d[f"load_lag_{lag}h"] = d["load_kw"].shift(lag)
    for w in [3,6,24]:
        d[f"load_roll_{w}h"] = d["load_kw"].rolling(w).mean()
    d["load_roll_std_24h"] = d["load_kw"].rolling(24).std()
    d["solar_lag_24h"]  = d["solar_kw"].shift(24)
    mx = d["solar_kw"].rolling(24).max().replace(0,1)
    d["cloud_factor"]   = (d["solar_kw"]/mx).clip(0,1)
    d["temp_roll_6h"]   = d["temp_c"].rolling(6).mean()
    d["peak_x_monsoon"] = d["is_evening_peak"]*d["is_monsoon"]
    d["peak_x_summer"]  = d["is_morning_peak"]*d["is_summer"]
    return d.dropna()


# 
# MODEL TRAINING
# 

@st.cache_resource(show_spinner=False)
def train(df_raw):
    df    = engineer(df_raw)
    if len(df) < MIN_MODEL_ROWS:
        raise ValueError(
            f"Need at least {MIN_MODEL_ROWS} usable rows after feature engineering; "
            f"got {len(df)}."
        )
    split = int(len(df)*0.82)
    Xtr   = df[FEATURES].iloc[:split]
    ytr   = df["load_kw"].iloc[:split]
    Xte   = df[FEATURES].iloc[split:]
    yte   = df["load_kw"].iloc[split:]

    model = xgb.XGBRegressor(
        n_estimators=700, max_depth=6, learning_rate=0.04,
        subsample=0.8, colsample_bytree=0.8,
        min_child_weight=3, reg_alpha=0.1, reg_lambda=1.0,
        random_state=42, verbosity=0
    )
    model.fit(Xtr, ytr)
    preds = np.clip(model.predict(Xte), 0, None)
    mae   = mean_absolute_error(yte, preds)
    mape  = float(np.mean(np.abs((yte-preds)/yte.clip(1)))*100)
    imp   = pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False)

    err_hr = {}
    for h in range(24):
        m = Xte.index.hour==h
        err_hr[h] = float(np.abs(yte[m]-preds[m]).mean()) if m.sum()>0 else 25.0

    return model, mae, mape, imp, Xte, yte, preds, err_hr


# 
# FORECAST ENGINE
# 

def forecast_24h(model, df_raw, err_hr, solar_cap=200, start_soc=72.0, bat_kwh=500.0):
    df_f   = engineer(df_raw)
    hist   = df_f.tail(400).copy()
    fc, up, lo, sol = [], [], [], []

    for step in range(24):
        nxt = hist.index[-1] + pd.Timedelta(hours=1)
        h, m = nxt.hour, nxt.month
        if 6<=h<=18:
            ang = np.sin((h-6)*np.pi/12)
            s   = solar_cap * ang
            cl  = 0.40 if m in [6,7,8,9] else 0.85 if m in [12,1,2] else 0.82
            solar_next = max(0.0, s*cl)
        else:
            solar_next = 0.0

        nr = pd.DataFrame({"load_kw":[hist["load_kw"].iloc[-1]],
                           "solar_kw":[solar_next],
                           "temp_c":[hist["temp_c"].iloc[-1]]}, index=[nxt])
        ext = pd.concat([hist, nr])
        ext = engineer(ext)

        X   = ext[FEATURES].iloc[-1:]
        if X.empty or X.isnull().values.any():
            # Not enough lag history for this step — use last known load
            p = float(hist["load_kw"].iloc[-1])
        else:
            p = float(np.clip(model.predict(X)[0], 80, 600))
        e   = err_hr.get(h, 25.0)
        fc.append(p); up.append(p+1.6*e); lo.append(max(0,p-1.6*e))
        sol.append(solar_next)

        nr["load_kw"] = p
        hist = pd.concat([hist, nr])

    # SoC simulation
    soc, cap, eta = float(start_soc), float(max(1, bat_kwh)), 0.95
    trace = [soc]
    for lv, sv in zip(fc, sol):
        net  = sv - lv
        dsoc = (net*eta/cap)*100*1.0
        soc  = float(np.clip(soc+dsoc, 10, 95))
        trace.append(soc)

    idx = [df_raw.index[-1]+pd.Timedelta(hours=i+1) for i in range(24)]
    fc_df = pd.DataFrame(
        {"fc_kw":fc,"up_kw":up,"lo_kw":lo,"solar_kw":sol,
         "net_kw":[s-l for s,l in zip(sol,fc)]},
        index=idx
    )
    return fc_df, trace


# 
# BRAIN
# 

def brain(fc_df, soc_trace, cur_soc, cur_load, cur_solar, cur_h, tariff, bat_kwh=500):
    alerts, tags = [], []
    min_soc  = min(soc_trace)
    min_step = soc_trace.index(min_soc)
    peak_kw  = fc_df["fc_kw"].max()
    peak_h   = fc_df["fc_kw"].idxmax().hour
    is_cheap = cur_h in tariff["cheap_hours"]
    is_peak  = cur_h in tariff["peak_hours"]
    peak_com = any(h in tariff["peak_hours"] for h in range(cur_h, min(cur_h+5,24)))
    net_now  = cur_solar - cur_load
    hrs_left = (cur_soc-10)*bat_kwh/max(1,abs(net_now)*100/95) if net_now<0 else 999

    if cur_soc < 20:
        alerts.append(("CRITICAL",
            f" Battery CRITICAL at {cur_soc:.0f}%. "
            f"Estimated {hrs_left:.1f}h before shutdown. Import from grid NOW.",
            "EMERGENCY CHARGE"))
        tags.append("dt-red")

    elif min_soc < 20:
        alerts.append(("WARNING",
            f" Battery forecast to reach {min_soc:.0f}% in {min_step}h. "
            f"Plan grid charging before that window.",
            "PLAN CHARGE"))
        tags.append("dt-blue")

    if is_cheap and cur_soc < 75 and not is_peak:
        saved = (75-cur_soc)/100*bat_kwh*(tariff["peak"]-tariff["cheap"])
        alerts.append(("INFO",
            f"Cheap tariff active at INR {tariff['cheap']}/kWh. "
            f"Charging now saves INR {saved:.0f} vs peak import.",
            "CHARGE NOW"))
        tags.append("dt-blue")

    if peak_com and cur_soc < 65 and is_cheap:
        hrs_to_peak = next((h for h in tariff["peak_hours"] if h>cur_h), 18)-cur_h
        alerts.append(("WARNING",
            f" Peak tariff starts in {hrs_to_peak}h. "
            f"Battery at {cur_soc:.0f}%  pre-charge to 80% at cheap rate.",
            "PRE-CHARGE"))
        tags.append("dt-amber")

    if peak_kw > 400:
        dc_save = (peak_kw-400)*0.15*tariff["demand_per_kw"]/30
        alerts.append(("WARNING",
            f"Demand peak {peak_kw:.0f} kW forecast at {peak_h}:00. "
            f"Battery shaving will save INR {dc_save:.0f} in demand charges.",
            "DEMAND SHAVE"))
        tags.append("dt-amber")

    if is_peak and cur_soc > 30 and net_now < 0:
        hr_save = abs(net_now)*(tariff["peak"]-tariff["normal"])
        alerts.append(("INFO",
            f"Peak rate INR {tariff['peak']}/kWh. "
            f"Battery covering {abs(net_now):.0f} kW, saving INR {hr_save:.0f}/hr.",
            "DISCHARGING"))
        tags.append("dt-amber")

    if not alerts:
        alerts.append(("OK",
            f" All systems normal. Battery {cur_soc:.0f}%, "
            f"{hrs_left:.0f}h reserve. Solar covering {cur_solar:.0f} kW.",
            "HOLD"))
        tags.append("dt-green")

    return alerts, tags


# 
# SOLAR HEALTH  Sunil's 4 detectors
# 

def solar_health_local(df, solar_cap=200):
    """Local fallback if backend /solar/health is unavailable."""
    alerts = []
    daytime_mask = (df.index.hour >= 9) & (df.index.hour <= 15)
    day = df[daytime_mask]

    if len(day) >= 4:
        avg_sol  = day["solar_kw"].mean()
        theory   = solar_cap * 0.65
        pr       = avg_sol / theory if theory > 0 else 1.0

        if pr < 0.75:
            alerts.append(("SOILING","WARNING",
                f"Performance Ratio {pr:.2f}  panels likely dirty. "
                f"Cleaning recovers ~{(0.95-pr)*theory:.0f} kW "
                f"({(0.95-pr)*theory*6.1*8:.0f}/day).",
                "Schedule panel cleaning"))
        elif pr < 0.85:
            alerts.append(("SOILING","INFO",
                f"Performance Ratio {pr:.2f}  slight degradation. Monitor.",
                "Watch over 3 days"))

    if len(df) >= 4:
        last4 = df.tail(4)["solar_kw"].values
        drop  = last4[0] - last4[-1]
        h_now = df.index[-1].hour
        if drop > 50 and 9<=h_now<=16:
            alerts.append(("SUDDEN_DROP","CRITICAL",
                f"Solar dropped {drop:.0f} kW in 1 hour with no cloud event. "
                f"Possible loose connection or inverter fault  fire risk.",
                "Inspect inverter and connections NOW"))

    if len(df) >= 7*24*2:
        tw = df.tail(7*48)["solar_kw"].mean()
        lw = df.tail(14*48).head(7*48)["solar_kw"].mean()
        if lw > 5:
            drop_pct = (lw-tw)/lw*100
            if drop_pct > 15:
                alerts.append(("DEGRADATION","WARNING",
                    f"Solar output down {drop_pct:.0f}% vs last week "
                    f"({tw:.0f} vs {lw:.0f} kW). "
                    f"Panel failure or soiling  thermographic scan recommended.",
                    "Arrange thermographic inspection"))

    return alerts


# 
# SAVINGS CALCULATOR
# 

def calc_savings(fc_df, tariff, bat_kwh=500):
    cheap_e = fc_df.loc[fc_df.index.hour.isin(tariff["cheap_hours"]),"fc_kw"].sum()
    peak_e  = fc_df.loc[fc_df.index.hour.isin(tariff["peak_hours"]), "fc_kw"].sum()
    arb     = min(cheap_e, bat_kwh)*(tariff["peak"]-tariff["cheap"])*0.35
    pk_dem  = fc_df["fc_kw"].max()
    dem_sav = pk_dem*0.15*tariff["demand_per_kw"]/30
    day     = arb + dem_sav
    return {"daily":day,"monthly":day*30,"annual":day*365,
            "arb":arb,"demand":dem_sav,"peak_kw":pk_dem}


# 
# PLOT HELPER
# 

def fig_base(h=320):
    f = go.Figure()
    f.update_layout(
        height=h,
        paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["panel"],
        font=dict(family="JetBrains Mono, monospace", color="#3d5a80", size=11),
        margin=dict(t=36,b=16,l=8,r=8),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.06,
                    bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#4a6fa5", size=11)),
        xaxis=dict(gridcolor=COLORS["gl"], zeroline=False,
                   tickfont=dict(color="#3d5a80", size=10)),
        yaxis=dict(gridcolor=COLORS["gl"], zeroline=False,
                   tickfont=dict(color="#3d5a80", size=10)),
    )
    return f


# 
#  SIDEBAR 
# 

with st.sidebar:
    st.markdown(
        '<div style="font-size:22px;font-weight:800;color:#e8eef7;'
        'letter-spacing:-0.5px;margin-bottom:2px">MicroGrid AI</div>'
        '<div style="font-family:JetBrains Mono,monospace;font-size:10px;'
        'color:#3d5a80;letter-spacing:3px;text-transform:uppercase;'
        'margin-bottom:16px">India Energy Intelligence</div>',
        unsafe_allow_html=True
    )
    st.divider()

    st.markdown('<div class="sb-label">Facility</div>', unsafe_allow_html=True)
    facility = st.selectbox("Facility", [
        "Apollo Multispeciality Hospital, Kolkata",
        "AMRI Hospital, Salt Lake",
        "Medica Superspecialty Hospital",
        "Fortis Hospital, Anandapur",
        "IIT Kharagpur Campus",
        "Jadavpur University",
        "IIM Calcutta, Joka",
        "Haldia Petrochemicals",
        "Custom Facility",
    ], label_visibility="collapsed")

    city = st.selectbox("City", list(CITIES.keys()))
    tariff_name = st.selectbox("State Tariff", list(INDIA_TARIFFS.keys()))
    tariff = INDIA_TARIFFS[tariff_name]

    st.divider()

    st.markdown('<div class="sb-label">System Specs</div>', unsafe_allow_html=True)
    bat_kwh   = st.slider("Battery (kWh)",  100, 2000, 500, 50)
    solar_cap = st.slider("Solar Array (kW)", 50, 500, 200, 10)
    cur_soc   = st.slider("Current SoC (%)", 10, 100, 68, 1)

    st.divider()

    st.markdown('<div class="sb-label">Data Source</div>', unsafe_allow_html=True)
    src = st.radio("Data Source", [
        "Live (Render backend)",
        "Upload CSV",
        "Demo mode",
    ], label_visibility="collapsed")

    uploaded = None
    if src == "Upload CSV":
        uploaded = st.file_uploader(
            "Inverter / meter CSV",
            type=["csv"],
            label_visibility="collapsed"
        )
        st.caption("Sungrow / Huawei / SolarEdge / Growatt / any meter CSV")

    st.divider()

    if st.button("Simulate Next Reading"):
        try:
            r = requests.post(f"{BACKEND_URL}/simulate/tick", timeout=35)
            if r.status_code == 200:
                d = r.json().get("reading", {})
                st.success(
                    f"Reading added\n"
                    f"Load {d.get('load_kw')} kW | "
                    f"SoC {d.get('battery_soc')}%"
                )
                st.cache_data.clear()
            else:
                st.error(f"Backend error {r.status_code}")
        except Exception as e:
            st.error(f"Backend offline: {e}")

    if st.button("Refresh Dashboard"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption(
        "MicroGrid AI v2.0\n"
        "Built for India's mid-market\n"
        f" 2026  Kolkata"
    )


# 
#  LOAD DATA 
# 

data_tag = "demo"

if src == "Live (Render backend)":
    with st.spinner("Connecting to live backend..."):
        df_backend, tag, backend_err = fetch_backend(hours=max(600, MIN_HISTORY_HOURS))
    if df_backend is not None:
        for col in ["load_kw","solar_kw","temp_c"]:
            if col not in df_backend.columns:
                df_backend[col] = 0.0
        df_raw  = df_backend
        data_tag = "live"
        live_reading = fetch_live()
        if live_reading:
            cur_soc   = float(live_reading.get("battery_soc", cur_soc))
        backend_stats = fetch_stats()
    else:
        st.sidebar.error(
            f"Backend unavailable — showing demo data.\n\n"
            f"Reason: {backend_err}"
        )
        df_raw = synthetic_data(n_days=365, solar_kw=solar_cap)
        live_reading  = None
        backend_stats = None

elif src == "Upload CSV" and uploaded is not None:
    df_raw = parse_csv(uploaded)
    if df_raw is None or len(df_raw) < MIN_HISTORY_HOURS:
        st.warning(f"Need at least {MIN_HISTORY_HOURS} hourly rows. Using demo data.")
        df_raw = synthetic_data(n_days=365, solar_kw=solar_cap)
    else:
        data_tag = "csv"
    live_reading  = None
    backend_stats = None

else:
    df_raw = synthetic_data(n_days=365, solar_kw=solar_cap)
    live_reading  = None
    backend_stats = None

if len(engineer(df_raw)) < MIN_MODEL_ROWS:
    st.warning("Not enough usable rows after feature engineering. Using demo data.")
    df_raw = synthetic_data(n_days=365, solar_kw=solar_cap)
    live_reading = None
    backend_stats = None


# 
#  TRAIN + FORECAST 
# 

with st.spinner("Training XGBoost model..."):
    model, mae, mape, imp, Xte, yte, test_preds, err_hr = train(df_raw)

with st.spinner("Generating 24-hour forecast..."):
    fc_df, soc_trace = forecast_24h(model, df_raw, err_hr, solar_cap, cur_soc, bat_kwh)


# 
#  CURRENT VALUES 
# 

cur = df_raw.iloc[-1]

# Use live reading if available, else last row of data
if live_reading:
    cur_load  = float(live_reading.get("load_kw",  cur["load_kw"]))
    cur_solar = float(live_reading.get("solar_kw", cur["solar_kw"]))
    cur_soc   = float(live_reading.get("battery_soc", cur_soc))
    cur_temp  = float(live_reading.get("battery_temp", cur.get("temp_c", 28)))
else:
    cur_load  = float(cur["load_kw"])
    cur_solar = float(cur["solar_kw"])
    cur_temp  = float(cur.get("temp_c", 28))

cur_h   = pd.Timestamp.now().hour
net_now = cur_solar - cur_load
savings = calc_savings(fc_df, tariff, bat_kwh)


# 
#  BRAIN & HEALTH 
# 

alerts, dtags = brain(
    fc_df, soc_trace,
    cur_soc, cur_load, cur_solar,
    cur_h, tariff, bat_kwh
)

# Solar health  try backend first, local fallback
health_data = fetch_health()
if health_data and health_data.get("alerts"):
    solar_alerts = [
        (a["type"], a["severity"], a["message"], a["action"])
        for a in health_data["alerts"]
    ]
else:
    solar_alerts = solar_health_local(df_raw, solar_cap)


# 
#  HEADER 
# 

c_title, c_badge = st.columns([5, 1])
with c_title:
    st.markdown(
        f'<div class="pg-title">{facility}</div>'
        f'<div class="pg-sub">{city}  {tariff_name}  '
        f'{pd.Timestamp.now().strftime("%d %b %Y, %I:%M %p")}</div>',
        unsafe_allow_html=True
    )
with c_badge:
    label_map = {
        "live": " LIVE DATA",
        "csv" : " CSV DATA",
        "demo": " DEMO MODE",
    }
    color_map = {
        "live": "#10b981",
        "csv" : "#3b82f6",
        "demo": "#f59e0b",
    }
    clr = color_map.get(data_tag, "#f59e0b")
    lbl = label_map.get(data_tag, " DEMO")
    st.markdown(
        f'<div style="margin-top:14px">'
        f'<div class="live-dot" style="border-color:rgba(99,99,99,0.3);color:{clr}">'
        f'<div class="pulse" style="background:{clr}"></div>'
        f'<span style="font-size:10px">{lbl}</span>'
        f'</div></div>',
        unsafe_allow_html=True
    )


# 
#  METRIC ROW 
# 

m1,m2,m3,m4,m5,m6 = st.columns(6)

soc_delta = " Draining" if net_now < 0 else " Charging"
m1.metric("Battery SoC",   f"{cur_soc:.0f}%",   soc_delta)
m2.metric("Load Now",      f"{cur_load:.0f} kW")
m3.metric("Solar Now",     f"{cur_solar:.0f} kW")
m4.metric("AI Accuracy",   f"{max(0,100-mape):.1f}%", f"MAE {mae:.0f} kW")
m5.metric("24h Peak",      f"{fc_df['fc_kw'].max():.0f} kW",
          f"at {fc_df['fc_kw'].idxmax().strftime('%H:%M')}")
m6.metric("Min SoC (24h)", f"{min(soc_trace):.0f}%",
          " Low" if min(soc_trace)<25 else " Safe",
          delta_color="inverse" if min(soc_trace)<25 else "normal")


# 
#  BRAIN DECISIONS 
# 

st.markdown('<div class="sec-label">Brain Decisions</div>', unsafe_allow_html=True)

tags_html = "".join(
    f'<span class="dtag {dtags[i]}">{alerts[i][2]}</span>'
    for i in range(len(alerts))
)
st.markdown(tags_html, unsafe_allow_html=True)
st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

css_map = {"CRITICAL":"a-critical","WARNING":"a-warning",
           "INFO":"a-info","OK":"a-ok"}
for sev, msg, _ in alerts:
    st.markdown(
        f'<div class="{css_map.get(sev,"a-info")}">{msg}</div>',
        unsafe_allow_html=True
    )


# 
#  SOLAR HEALTH ALERTS 
# 

if solar_alerts:
    st.markdown(
        '<div class="sec-label">Solar Health Monitoring</div>',
        unsafe_allow_html=True
    )
    for alrt in solar_alerts:
        atype, asev, amsg, aact = alrt
        css = "a-critical" if asev=="CRITICAL" else "a-warning" if asev=="WARNING" else "a-solar"
        st.markdown(
            f'<div class="{css}">'
            f'<strong>{atype.replace("_"," ")}</strong>  {amsg}<br>'
            f'<span style="opacity:0.7;font-size:12px"> {aact}</span>'
            f'</div>',
            unsafe_allow_html=True
        )


# 
#  CHART 1: POWER BALANCE (7 days) 
# 

st.markdown('<div class="sec-label">Power Balance  Last 7 Days</div>', unsafe_allow_html=True)

week = df_raw.tail(7*24)
f1   = fig_base(300)

f1.add_trace(go.Scatter(
    x=week.index, y=week["load_kw"],
    name="Load (kW)",
    line=dict(color=COLORS["load"], width=1.5),
    hovertemplate="%{y:.0f} kW<extra>Load</extra>"
))
f1.add_trace(go.Scatter(
    x=week.index, y=week["solar_kw"],
    name="Solar (kW)",
    line=dict(color=COLORS["solar"], width=1.5),
    fill="tozeroy", fillcolor="rgba(245,158,11,0.06)",
    hovertemplate="%{y:.0f} kW<extra>Solar</extra>"
))
net_s = (week["solar_kw"]-week["load_kw"]).clip(lower=0)
f1.add_trace(go.Scatter(
    x=week.index, y=net_s,
    name="Solar surplus",
    line=dict(width=0),
    fill="tozeroy", fillcolor="rgba(16,185,129,0.05)",
    showlegend=False
))
f1.add_hrect(
    y0=420, y1=600,
    fillcolor="rgba(239,68,68,0.04)", line_width=0,
    annotation_text="Demand charge zone",
    annotation_font=dict(color="#ef4444", size=10),
    annotation_position="top right"
)
st.plotly_chart(f1, use_container_width=True)


# 
#  CHART 2: AI FORECAST (24h load + SoC) 
# 

st.markdown('<div class="sec-label">AI Forecast  Next 24 Hours</div>', unsafe_allow_html=True)

f2 = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.06,
    row_heights=[0.62, 0.38]
)

# Confidence band
f2.add_trace(go.Scatter(
    x=list(fc_df.index)+list(fc_df.index[::-1]),
    y=list(fc_df["up_kw"])+list(fc_df["lo_kw"][::-1]),
    fill="toself", fillcolor=COLORS["conf"],
    line=dict(color="rgba(0,0,0,0)"),
    name="Confidence band", hoverinfo="skip"
), row=1, col=1)

f2.add_trace(go.Scatter(
    x=fc_df.index, y=fc_df["fc_kw"],
    name="AI Load Forecast",
    line=dict(color=COLORS["fc"], width=2.5),
    hovertemplate="%{y:.0f} kW<extra>Forecast</extra>"
), row=1, col=1)

f2.add_trace(go.Scatter(
    x=fc_df.index, y=fc_df["solar_kw"],
    name="Solar Forecast",
    line=dict(color=COLORS["solar"], width=1.5, dash="dot"),
    hovertemplate="%{y:.0f} kW<extra>Solar</extra>"
), row=1, col=1)

f2.add_hline(y=420, row=1, col=1,
    line=dict(color="rgba(239,68,68,0.5)", width=1, dash="dash"),
    annotation=dict(text="Demand limit 420 kW",
                    font=dict(color="#ef4444", size=10), xanchor="right"))

f2.add_trace(go.Scatter(
    x=fc_df.index, y=soc_trace[1:],
    name="Battery SoC",
    line=dict(color=COLORS["soc"], width=2.5),
    fill="tozeroy", fillcolor="rgba(16,185,129,0.06)",
    hovertemplate="%{y:.1f}%<extra>SoC</extra>"
), row=2, col=1)

for thresh, col, lbl in [(20,"rgba(239,68,68,0.7)","Critical 20%"),
                          (35,"rgba(245,158,11,0.6)","Warning 35%")]:
    f2.add_hline(y=thresh, row=2, col=1,
        line=dict(color=col, width=1, dash="dot"),
        annotation=dict(text=lbl,
                        font=dict(color=col, size=10), xanchor="right"))

f2.update_layout(
    height=460,
    paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["panel"],
    font=dict(family="JetBrains Mono, monospace", color="#3d5a80", size=11),
    margin=dict(t=20,b=16,l=8,r=8),
    hovermode="x unified",
    legend=dict(orientation="h", y=1.04,
                bgcolor="rgba(0,0,0,0)",
                font=dict(color="#4a6fa5", size=11))
)
f2.update_xaxes(gridcolor=COLORS["gl"], zeroline=False)
f2.update_yaxes(gridcolor=COLORS["gl"], zeroline=False)
f2.update_yaxes(title_text="kW",    row=1, col=1,
                title_font=dict(color="#3d5a80",size=11))
f2.update_yaxes(title_text="SoC %", row=2, col=1,
                range=[0,100],
                title_font=dict(color="#3d5a80",size=11))
st.plotly_chart(f2, use_container_width=True)


# 
#  CHART 3: BACKTEST + FEATURE IMPORTANCE 
# 

st.markdown('<div class="sec-label">Model Performance</div>', unsafe_allow_html=True)

cb, cf = st.columns([3,2])

with cb:
    hrs = min(168, len(yte))
    f3  = fig_base(260)
    f3.add_trace(go.Scatter(
        y=yte.values[:hrs], name="Actual",
        line=dict(color=COLORS["load"], width=1.5)
    ))
    f3.add_trace(go.Scatter(
        y=test_preds[:hrs], name="AI Predicted",
        line=dict(color=COLORS["fc"], width=1.5, dash="dot")
    ))
    f3.update_layout(title=dict(
        text="Backtest  Actual vs AI Predicted (1 Week Sample)",
        font=dict(color="#4a6fa5", size=12), x=0.01
    ))
    st.plotly_chart(f3, use_container_width=True)

with cf:
    st.markdown(
        '<div style="font-family:JetBrains Mono,monospace;font-size:11px;'
        'color:#3d5a80;margin:8px 0 14px;letter-spacing:1px">'
        'TOP PREDICTIVE FEATURES</div>',
        unsafe_allow_html=True
    )
    top5 = imp.head(5)
    mx   = float(top5.iloc[0])
    bar_clr = {"lag":"#2563eb","roll":"#10b981"}
    for feat, score in top5.items():
        lbl = feat.replace("load_","").replace("_h","h").replace("_"," ").title()
        pct = score/mx*100
        bc  = "#2563eb" if "lag" in feat else "#10b981" if "roll" in feat else "#f59e0b"
        st.markdown(
            f'<div class="fi-row">'
            f'<div class="fi-label"><span>{lbl}</span>'
            f'<span style="color:#e8eef7">{score:.3f}</span></div>'
            f'<div class="fi-track">'
            f'<div class="fi-fill" style="width:{pct:.0f}%;background:{bc}"></div>'
            f'</div></div>',
            unsafe_allow_html=True
        )
    acc = max(0, 100-mape)
    for lbl2, val2, clr2 in [
        ("MAE",      f"{mae:.1f} kW", "#e8eef7"),
        ("MAPE",     f"{mape:.1f}%",  "#e8eef7"),
        ("Accuracy", f"{acc:.1f}%",   "#10b981"),
    ]:
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;'
            f'padding:8px 0;border-bottom:1px solid #1c2d47;'
            f'font-family:JetBrains Mono,monospace;font-size:12px">'
            f'<span style="color:#3d5a80">{lbl2}</span>'
            f'<span style="color:{clr2};font-weight:600">{val2}</span>'
            f'</div>',
            unsafe_allow_html=True
        )


# 
#  SAVINGS CALCULATOR 
# 

st.markdown('<div class="sec-label">India Tariff Savings Calculator</div>', unsafe_allow_html=True)

s1,s2,s3,s4 = st.columns(4)
payback = 40000/max(1, savings["monthly"])

for col, val, lbl in [
    (s1, f"INR {savings['daily']:,.0f}",             "Daily saving"),
    (s2, f"INR {savings['monthly']/1000:.1f}K",      "Monthly saving"),
    (s3, f"INR {savings['annual']/100000:.1f}L",     "Annual saving"),
    (s4, f"{payback:.1f} months",                  "Payback period"),
]:
    col.markdown(
        f'<div class="sav-card">'
        f'<div class="sav-val">{val}</div>'
        f'<div class="sav-lab">{lbl}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

st.markdown(
    f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;'
    f'color:#3d5a80;margin-top:10px;text-align:center;letter-spacing:1px">'
    f'{tariff_name} | INR {tariff["cheap"]}/kWh cheap | '
    f'INR {tariff["normal"]}/kWh normal | INR {tariff["peak"]}/kWh peak | '
    f'INR {tariff["demand_per_kw"]}/kW demand charge | '
    f'Software fee: INR 40,000/month</div>',
    unsafe_allow_html=True
)


# 
#  TARIFF RATE CHART 
# 

st.markdown('<div class="sec-label">ToD Tariff Rate  Next 24 Hours</div>', unsafe_allow_html=True)

rates  = [tariff["cheap"]  if h in tariff["cheap_hours"] else
          tariff["peak"]   if h in tariff["peak_hours"]  else
          tariff["normal"] for h in range(24)]
colors_bar = ["#10b981" if h in tariff["cheap_hours"] else
              "#ef4444" if h in tariff["peak_hours"]  else
              "#2563eb" for h in range(24)]

f4 = fig_base(200)
f4.add_trace(go.Bar(
    x=list(range(24)), y=rates,
    marker_color=colors_bar,
    hovertemplate="Hour %{x}:00 | INR %{y}/kWh<extra></extra>"
))
f4.add_vline(x=cur_h,
    line=dict(color="rgba(255,255,255,0.6)", width=1.5, dash="dash"),
    annotation=dict(text="Now", font=dict(color="white", size=11))
)
f4.update_layout(
    showlegend=False,
    title=dict(
        text="Cheap hours | Normal | Peak hours",
        font=dict(color="#3d5a80", size=11), x=0.5, xanchor="center"
    ),
    xaxis=dict(tickmode="array",
               tickvals=list(range(0,24,2)),
               ticktext=[f"{h:02d}:00" for h in range(0,24,2)]),
    yaxis=dict(title="INR/kWh")
)
st.plotly_chart(f4, use_container_width=True)


# 
#  BACKEND STATS (if live) 
# 

if data_tag == "live" and backend_stats:
    st.markdown(
        '<div class="sec-label">Live Backend Stats</div>',
        unsafe_allow_html=True
    )
    bs1,bs2,bs3,bs4 = st.columns(4)
    bs1.metric("Avg Load",    f"{backend_stats.get('avg_load_kw',0):.0f} kW")
    bs2.metric("Peak Load",   f"{backend_stats.get('peak_load_kw',0):.0f} kW")
    bs3.metric("Avg Solar",   f"{backend_stats.get('avg_solar_kw',0):.0f} kW")
    bs4.metric("Total Readings", f"{backend_stats.get('total_readings',0):,}")


# 
#  FOOTER 
# 

st.markdown(
    f'<div style="margin-top:48px;padding:20px 0;'
    f'border-top:1px solid #1c2d47;'
    f'display:flex;justify-content:space-between;'
    f'align-items:center;flex-wrap:wrap;gap:8px">'
    f'<div style="font-family:JetBrains Mono,monospace;'
    f'font-size:10px;color:#1c2d47;letter-spacing:2px">'
    f'MICROGRID AI  INDIA-NATIVE ENERGY INTELLIGENCE  '
    f'BUILT FOR THE MID-MARKET</div>'
    f'<div style="font-family:JetBrains Mono,monospace;'
    f'font-size:10px;color:#1c2d47">'
    f'XGBoost {xgb.__version__}  '
    f'{len(df_raw)} hrs training data  '
    f'{pd.Timestamp.now().strftime("%d %b %Y")}'
    f'</div></div>',
    unsafe_allow_html=True
)
