# dashboard.py
# MicroGrid AI — with real XGBoost forecast engine
# Deployable on Streamlit Cloud — no external files needed

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import xgboost as xgb
from sklearn.metrics import mean_absolute_error
import warnings
warnings.filterwarnings('ignore')

# ── PAGE CONFIG ──
st.set_page_config(
    page_title="MicroGrid AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CUSTOM CSS — makes it look professional ──
st.markdown("""
<style>
    /* Main background */
    .stApp { background-color: #0f1117; }

    /* Metric cards */
    div[data-testid="metric-container"] {
        background: #1a1d2e;
        border: 1px solid #2d3561;
        border-radius: 10px;
        padding: 16px;
    }
    div[data-testid="metric-container"] label {
        color: #7c8db5 !important;
        font-size: 12px !important;
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #e2e8f0 !important;
        font-size: 28px !important;
        font-weight: 600 !important;
    }

    /* Sidebar */
    .css-1d391kg { background-color: #1a1d2e; }
    section[data-testid="stSidebar"] { background: #1a1d2e; }

    /* Headers */
    h1, h2, h3 { color: #e2e8f0 !important; }

    /* Alert boxes */
    .alert-critical {
        background: rgba(239,68,68,0.12);
        border: 1px solid rgba(239,68,68,0.4);
        border-radius: 8px;
        padding: 12px 16px;
        color: #fca5a5;
        font-size: 14px;
        margin: 8px 0;
    }
    .alert-warning {
        background: rgba(245,158,11,0.12);
        border: 1px solid rgba(245,158,11,0.4);
        border-radius: 8px;
        padding: 12px 16px;
        color: #fcd34d;
        font-size: 14px;
        margin: 8px 0;
    }
    .alert-info {
        background: rgba(59,130,246,0.12);
        border: 1px solid rgba(59,130,246,0.4);
        border-radius: 8px;
        padding: 12px 16px;
        color: #93c5fd;
        font-size: 14px;
        margin: 8px 0;
    }
    .alert-ok {
        background: rgba(16,185,129,0.12);
        border: 1px solid rgba(16,185,129,0.4);
        border-radius: 8px;
        padding: 12px 16px;
        color: #6ee7b7;
        font-size: 14px;
        margin: 8px 0;
    }

    /* Section headers */
    .section-header {
        font-size: 11px;
        letter-spacing: 3px;
        text-transform: uppercase;
        color: #4a6fa5;
        margin: 24px 0 12px;
        padding-bottom: 8px;
        border-bottom: 1px solid #2d3561;
    }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════
# DATA GENERATION
# Generates realistic Indian hospital data
# Replace with real customer data later
# ════════════════════════════════════════════

@st.cache_data
def generate_training_data(n_days=400, seed=42):
    """
    Generates 400 days of realistic Kolkata hospital energy data.
    Includes: monsoon effects, ToD patterns, seasonal variation.
    Cached — only runs once per session.
    """
    np.random.seed(seed)
    hours = pd.date_range('2023-06-01', periods=n_days * 24, freq='1h')

    load, solar, temp = [], [], []

    for ts in hours:
        h, m, dow = ts.hour, ts.month, ts.dayofweek

        # Base hospital load
        base = 290

        # Time of day pattern
        if 8 <= h <= 11:    base += 110   # morning peak
        elif 13 <= h <= 15: base += 50    # post-lunch equipment
        elif 18 <= h <= 22: base += 80    # evening peak
        elif 0 <= h <= 5:   base -= 65    # night minimum

        # Seasonal
        if m in [4, 5, 6]:  base += 45   # summer HVAC
        if m in [7, 8, 9]:  base += 28   # monsoon humidity

        # Weekend slightly lower
        if dow >= 5:        base -= 18

        load.append(max(150, base + np.random.normal(0, 20)))

        # Solar — Kolkata specific
        if 6 <= h <= 18:
            angle = np.sin((h - 6) * np.pi / 12)
            s = 195 * angle

            # Monsoon cloud reduction
            if m in [6, 7, 8, 9]:
                # Heavy cloud variability during monsoon
                cloud = np.random.beta(1.5, 5)
                s *= cloud
            elif m in [12, 1, 2]:
                cloud = np.random.beta(7, 2)   # mostly clear winter
                s *= cloud
            else:
                cloud = np.random.beta(6, 2)
                s *= cloud

            solar.append(max(0, s + np.random.normal(0, 8)))
        else:
            solar.append(0.0)

        # Temperature — Kolkata annual pattern
        t = 28 + 8 * np.sin((m - 4) * np.pi / 6) + np.random.normal(0, 1.5)
        temp.append(t)

    df = pd.DataFrame({
        'timestamp': hours,
        'load_kw'  : load,
        'solar_kw' : solar,
        'temp_c'   : temp,
    }).set_index('timestamp')

    return df


# ════════════════════════════════════════════
# FEATURE ENGINEERING
# ════════════════════════════════════════════

def add_features(df):
    """Add all ML features — time + lag + rolling + interaction"""
    d = df.copy()

    # Cyclical time encoding (hour 23 stays close to hour 0)
    d['hour_sin']  = np.sin(2 * np.pi * d.index.hour / 24)
    d['hour_cos']  = np.cos(2 * np.pi * d.index.hour / 24)
    d['dow_sin']   = np.sin(2 * np.pi * d.index.dayofweek / 7)
    d['dow_cos']   = np.cos(2 * np.pi * d.index.dayofweek / 7)
    d['month_sin'] = np.sin(2 * np.pi * d.index.month / 12)
    d['month_cos'] = np.cos(2 * np.pi * d.index.month / 12)

    # Binary flags
    d['is_weekend']      = (d.index.dayofweek >= 5).astype(int)
    d['is_monsoon']      = d.index.month.isin([6, 7, 8, 9]).astype(int)
    d['is_morning_peak'] = d.index.hour.isin(range(8, 12)).astype(int)
    d['is_evening_peak'] = d.index.hour.isin(range(18, 23)).astype(int)
    d['is_tod_cheap']    = d.index.hour.isin(range(10, 16)).astype(int)
    d['is_night']        = d.index.hour.isin(list(range(0, 6))).astype(int)

    # Lag features
    for lag in [1, 2, 3, 6, 12, 24, 48, 168]:
        d[f'load_lag_{lag}h'] = d['load_kw'].shift(lag)

    # Rolling features
    for w in [3, 6, 24, 48]:
        d[f'load_roll_{w}h']   = d['load_kw'].rolling(w).mean()
    d['load_roll_std_24h'] = d['load_kw'].rolling(24).std()

    # Solar lags
    d['solar_lag_24h']  = d['solar_kw'].shift(24)
    d['solar_roll_6h']  = d['solar_kw'].rolling(6).mean()

    # Temperature
    d['temp_roll_6h'] = d['temp_c'].rolling(6).mean()

    # Interactions
    d['peak_x_monsoon'] = d['is_evening_peak'] * d['is_monsoon']
    d['peak_x_summer']  = d['is_morning_peak'] * (d.index.month.isin([4,5,6])).astype(int)

    return d.dropna()


FEATURES = [
    'hour_sin','hour_cos','dow_sin','dow_cos','month_sin','month_cos',
    'is_weekend','is_monsoon','is_morning_peak','is_evening_peak',
    'is_tod_cheap','is_night',
    'load_lag_1h','load_lag_2h','load_lag_3h','load_lag_6h',
    'load_lag_12h','load_lag_24h','load_lag_48h','load_lag_168h',
    'load_roll_3h','load_roll_6h','load_roll_24h','load_roll_48h',
    'load_roll_std_24h',
    'solar_lag_24h','solar_roll_6h',
    'temp_c','temp_roll_6h',
    'peak_x_monsoon','peak_x_summer',
]


# ════════════════════════════════════════════
# MODEL TRAINING
# Trains XGBoost — cached, runs only once
# ════════════════════════════════════════════

@st.cache_resource
def train_model(df):
    """
    Trains XGBoost on historical data.
    Uses walk-forward split — no data leakage.
    Returns trained model + accuracy metrics.
    """
    df_feat = add_features(df)

    # Walk-forward split: train on 85%, test on last 15%
    split   = int(len(df_feat) * 0.85)
    X_train = df_feat[FEATURES].iloc[:split]
    y_train = df_feat['load_kw'].iloc[:split]
    X_test  = df_feat[FEATURES].iloc[split:]
    y_test  = df_feat['load_kw'].iloc[split:]

    model = xgb.XGBRegressor(
        n_estimators      = 600,
        max_depth         = 6,
        learning_rate     = 0.04,
        subsample         = 0.8,
        colsample_bytree  = 0.8,
        min_child_weight  = 3,
        reg_alpha         = 0.1,
        reg_lambda        = 1.0,
        random_state      = 42,
        verbosity         = 0,
    )
    model.fit(X_train, y_train)

    preds = np.clip(model.predict(X_test), 0, None)
    mae   = mean_absolute_error(y_test, preds)
    mape  = np.mean(np.abs((y_test - preds) / y_test)) * 100

    # Feature importance
    importance = pd.Series(
        model.feature_importances_,
        index=FEATURES
    ).sort_values(ascending=False)

    return model, mae, mape, importance, X_test, y_test, preds


# ════════════════════════════════════════════
# FORECAST ENGINE
# Generates 24h ahead load + solar + SoC
# ════════════════════════════════════════════

def generate_24h_forecast(model, df, history_rows=400):
    """
    Generates 24-hour ahead forecasts for load, solar, and battery SoC.
    Also generates confidence bands (±1 std of recent errors).
    """
    df_feat  = add_features(df)
    history  = df_feat.tail(history_rows).copy()
    forecasts, uppers, lowers = [], [], []

    # Estimate uncertainty from recent prediction errors
    recent_X    = history[FEATURES].tail(168)
    recent_y    = history['load_kw'].tail(168)
    recent_pred = np.clip(model.predict(recent_X), 0, None)
    recent_err  = np.abs(recent_y.values - recent_pred)
    err_by_hour = {}
    for h in range(24):
        mask = recent_X.index.hour == h
        if mask.sum() > 0:
            err_by_hour[h] = recent_err[mask].mean()
        else:
            err_by_hour[h] = 20.0

    temp_history = history.copy()

    for step in range(24):
        next_time = temp_history.index[-1] + pd.Timedelta(hours=1)
        h         = next_time.hour
        m         = next_time.month
        dow       = next_time.dayofweek

        # Build feature row
        row = {
            'load_kw' : temp_history['load_kw'].iloc[-1],
            'solar_kw': 0.0,
            'temp_c'  : temp_history['temp_c'].iloc[-1],
        }
        tmp_row = pd.DataFrame([row], index=[next_time])
        extended = pd.concat([temp_history, tmp_row])
        extended = add_features(extended)

        X_step  = extended[FEATURES].iloc[-1:]
        pred    = float(np.clip(model.predict(X_step)[0], 100, 500))
        err     = err_by_hour.get(h, 20.0)

        forecasts.append(pred)
        uppers.append(pred + 1.5 * err)
        lowers.append(max(0, pred - 1.5 * err))

        # Add prediction back to history
        new_row              = tmp_row.copy()
        new_row['load_kw']   = pred
        temp_history         = pd.concat([temp_history, new_row])

    # Solar forecast — physics based
    solar_forecast = []
    for step in range(24):
        ft = df.index[-1] + pd.Timedelta(hours=step + 1)
        h, m = ft.hour, ft.month
        if 6 <= h <= 18:
            angle = np.sin((h - 6) * np.pi / 12)
            s     = 195 * angle
            if m in [6, 7, 8, 9]: s *= 0.40   # monsoon reduction
            elif m in [12, 1, 2]: s *= 0.85
            else:                 s *= 0.82
            solar_forecast.append(max(0, s))
        else:
            solar_forecast.append(0.0)

    # Battery SoC simulation
    soc          = 72.0   # starting SoC
    capacity_kwh = 500.0
    efficiency   = 0.95
    soc_trace    = [soc]

    for load, solar in zip(forecasts, solar_forecast):
        net       = solar - load
        delta_soc = (net * efficiency / capacity_kwh) * 100
        soc       = float(np.clip(soc + delta_soc, 10, 95))
        soc_trace.append(soc)

    hours_ahead = [
        df.index[-1] + pd.Timedelta(hours=i + 1)
        for i in range(24)
    ]

    forecast_df = pd.DataFrame({
        'timestamp'   : hours_ahead,
        'forecast_kw' : forecasts,
        'upper_kw'    : uppers,
        'lower_kw'    : lowers,
        'solar_kw'    : solar_forecast,
        'net_kw'      : [s - l for s, l in zip(solar_forecast, forecasts)],
    }).set_index('timestamp')

    return forecast_df, soc_trace


# ════════════════════════════════════════════
# BRAIN — DECISIONS & ALERTS
# ════════════════════════════════════════════

def run_brain(forecast_df, soc_trace, current_soc, current_hour):
    """
    Analyses forecasts and generates decisions + alerts.
    """
    alerts    = []
    decisions = []

    min_soc       = min(soc_trace)
    min_soc_hour  = soc_trace.index(min_soc)
    is_tod_cheap  = 10 <= current_hour <= 16
    is_peak       = 18 <= current_hour <= 22
    peak_load     = forecast_df['forecast_kw'].max()
    peak_load_hr  = forecast_df['forecast_kw'].idxmax().hour

    # Critical SoC
    if current_soc < 20:
        alerts.append(('CRITICAL', f'🔴 Battery at {current_soc:.0f}% — CRITICAL. Import from grid immediately.'))
        decisions.append('EMERGENCY_CHARGE')

    elif min_soc < 20:
        alerts.append(('WARNING', f'🟡 Battery forecast to reach {min_soc:.0f}% in {min_soc_hour}h. Plan charging now.'))
        decisions.append('PLAN_CHARGE')

    # Tariff arbitrage opportunity
    if is_tod_cheap and current_soc < 70:
        alerts.append(('INFO', f'🔵 Cheap tariff active (until 4 PM). Pre-charging battery saves money vs peak rates.'))
        decisions.append('CHARGE_CHEAP')

    # Peak demand warning
    if peak_load > 400:
        alerts.append(('WARNING', f'🟡 Demand peak of {peak_load:.0f} kW forecast at {peak_load_hr}:00. Battery dispatch will shave this automatically.'))
        decisions.append('DEMAND_SHAVE')

    # Evening peak preparation
    if 14 <= current_hour <= 17 and current_soc < 65:
        alerts.append(('WARNING', f'🟡 Evening peak in {18 - current_hour}h. Battery at {current_soc:.0f}% — recommend charging to 75% before 6 PM.'))
        decisions.append('PRECHARGE_FOR_PEAK')

    # All good
    if not alerts:
        hrs_left = (current_soc - 20) * 500 / (forecast_df['forecast_kw'].mean() * 100 / 95)
        alerts.append(('OK', f'🟢 System stable. Battery has ~{hrs_left:.1f}h reserve at current demand. No action needed.'))
        decisions.append('HOLD')

    return alerts, decisions


# ════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════

with st.sidebar:
    st.markdown("### ⚡ MicroGrid AI")
    st.markdown("*Energy Intelligence Platform*")
    st.divider()

    st.markdown("**Facility Settings**")

    facility_name = st.selectbox(
        "Facility",
        ["Apollo Hospital, Kolkata",
         "AMRI Hospital, Salt Lake",
         "IIT Kharagpur Campus",
         "Custom Facility"]
    )

    battery_kwh = st.slider(
        "Battery Capacity (kWh)", 100, 1000, 500, 50
    )

    solar_kw = st.slider(
        "Solar Array (kW)", 50, 500, 200, 10
    )

    current_soc = st.slider(
        "Current Battery SoC (%)", 10, 100, 68, 1
    )

    state_tariff = st.selectbox(
        "State Tariff",
        ["West Bengal (CESC)",
         "Maharashtra (MSEDCL)",
         "Tamil Nadu (TANGEDCO)",
         "Karnataka (BESCOM)"]
    )

    st.divider()
    st.markdown("**Tariff Rates**")

    tariff_map = {
        "West Bengal (CESC)"       : (4.20, 6.10, 7.85),
        "Maharashtra (MSEDCL)"     : (3.80, 5.90, 8.20),
        "Tamil Nadu (TANGEDCO)"    : (4.50, 6.40, 8.10),
        "Karnataka (BESCOM)"       : (4.10, 6.00, 7.70),
    }
    cheap, normal, peak_rate = tariff_map[state_tariff]

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Cheap", f"₹{cheap}")
    col_b.metric("Normal", f"₹{normal}")
    col_c.metric("Peak", f"₹{peak_rate}")

    st.divider()
    st.caption(f"Built by [Your Name]\nMicroGrid AI v1.0\nKolkata, India")


# ════════════════════════════════════════════
# MAIN APP — LOAD DATA + TRAIN MODEL
# ════════════════════════════════════════════

current_hour = pd.Timestamp.now().hour

# Load data
with st.spinner("Loading energy data..."):
    df_raw = generate_training_data(n_days=400)

# Train model (cached — instant after first run)
with st.spinner("Training AI forecast model..."):
    model, mae, mape, importance, X_test, y_test, test_preds = train_model(df_raw)

# Get recent 7 days for display
df_recent = df_raw.tail(7 * 24)

# Generate 24h forecast
with st.spinner("Generating 24-hour forecast..."):
    forecast_df, soc_trace = generate_24h_forecast(model, df_raw)

# Run brain
alerts, decisions = run_brain(
    forecast_df, soc_trace, current_soc, current_hour
)


# ════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════

st.markdown(f"## ⚡ {facility_name}")
st.markdown(
    f"*AI Energy Management · {state_tariff} · "
    f"Updated {pd.Timestamp.now().strftime('%d %b %Y, %I:%M %p')}*"
)


# ════════════════════════════════════════════
# METRICS ROW
# ════════════════════════════════════════════

current = df_recent.iloc[-1]
net_now = current['solar_kw'] - current['load_kw']

col1, col2, col3, col4, col5, col6 = st.columns(6)

col1.metric(
    "Battery SoC",
    f"{current_soc}%",
    delta=f"{'↓' if net_now < 0 else '↑'} {abs(net_now):.0f} kW net"
)
col2.metric("Load Now",    f"{current['load_kw']:.0f} kW")
col3.metric("Solar Now",   f"{current['solar_kw']:.0f} kW")
col4.metric("Model MAE",   f"{mae:.1f} kW",   delta=f"{mape:.1f}% MAPE")
col5.metric("24h Peak",    f"{forecast_df['forecast_kw'].max():.0f} kW")
col6.metric("Min SoC (24h)", f"{min(soc_trace):.0f}%")


# ════════════════════════════════════════════
# BRAIN ALERTS
# ════════════════════════════════════════════

st.markdown('<div class="section-header">Brain Decisions</div>',
            unsafe_allow_html=True)

for severity, message in alerts:
    css_class = {
        'CRITICAL': 'alert-critical',
        'WARNING' : 'alert-warning',
        'INFO'    : 'alert-info',
        'OK'      : 'alert-ok',
    }.get(severity, 'alert-info')
    st.markdown(
        f'<div class="{css_class}">{message}</div>',
        unsafe_allow_html=True
    )


# ════════════════════════════════════════════
# CHART 1 — POWER BALANCE (last 7 days)
# ════════════════════════════════════════════

st.markdown('<div class="section-header">Power Balance — Last 7 Days</div>',
            unsafe_allow_html=True)

fig_balance = go.Figure()

fig_balance.add_trace(go.Scatter(
    x=df_recent.index,
    y=df_recent['load_kw'],
    name='Load (kW)',
    line=dict(color='#ef4444', width=1.5),
))
fig_balance.add_trace(go.Scatter(
    x=df_recent.index,
    y=df_recent['solar_kw'],
    name='Solar (kW)',
    line=dict(color='#f59e0b', width=1.5),
    fill='tozeroy',
    fillcolor='rgba(245,158,11,0.08)',
))
fig_balance.add_hrect(
    y0=400, y1=500,
    fillcolor='rgba(239,68,68,0.06)',
    line_width=0,
    annotation_text="Demand charge zone",
    annotation_font_color='#ef4444',
    annotation_font_size=11,
)

fig_balance.update_layout(
    height=320,
    paper_bgcolor='#0f1117',
    plot_bgcolor='#0f1117',
    font=dict(color='#7c8db5'),
    legend=dict(
        orientation='h', y=1.02,
        bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e2e8f0')
    ),
    xaxis=dict(gridcolor='#1a1d2e', showgrid=True),
    yaxis=dict(gridcolor='#1a1d2e', showgrid=True,
               title='kW', title_font_color='#7c8db5'),
    margin=dict(t=30, b=20, l=20, r=20),
    hovermode='x unified',
)

st.plotly_chart(fig_balance, use_container_width=True)


# ════════════════════════════════════════════
# CHART 2 — 24H AI FORECAST with confidence band
# ════════════════════════════════════════════

st.markdown('<div class="section-header">AI Forecast — Next 24 Hours</div>',
            unsafe_allow_html=True)

fig_forecast = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.08,
    subplot_titles=("Load Forecast (kW)", "Battery SoC Forecast (%)"),
    row_heights=[0.6, 0.4],
)

# Confidence band (shaded area between upper and lower)
fig_forecast.add_trace(go.Scatter(
    x=list(forecast_df.index) + list(forecast_df.index[::-1]),
    y=list(forecast_df['upper_kw']) + list(forecast_df['lower_kw'][::-1]),
    fill='toself',
    fillcolor='rgba(59,130,246,0.10)',
    line=dict(color='rgba(0,0,0,0)'),
    name='Confidence band',
    showlegend=True,
), row=1, col=1)

# Forecast line
fig_forecast.add_trace(go.Scatter(
    x=forecast_df.index,
    y=forecast_df['forecast_kw'],
    name='AI forecast',
    line=dict(color='#3b82f6', width=2.5),
    mode='lines',
), row=1, col=1)

# Solar forecast
fig_forecast.add_trace(go.Scatter(
    x=forecast_df.index,
    y=forecast_df['solar_kw'],
    name='Solar forecast',
    line=dict(color='#f59e0b', width=1.5, dash='dot'),
), row=1, col=1)

# Demand threshold line
fig_forecast.add_hline(
    y=400, row=1, col=1,
    line_dash='dash', line_color='#ef4444', line_width=1,
    annotation_text='Demand charge limit',
    annotation_font_color='#ef4444',
    annotation_font_size=10,
)

# SoC forecast
soc_colors = ['#ef4444' if s < 20 else '#f59e0b' if s < 35 else '#10b981'
              for s in soc_trace[1:]]

fig_forecast.add_trace(go.Scatter(
    x=forecast_df.index,
    y=soc_trace[1:],
    name='Battery SoC',
    line=dict(color='#10b981', width=2.5),
    fill='tozeroy',
    fillcolor='rgba(16,185,129,0.08)',
), row=2, col=1)

# SoC threshold lines
for thresh, color, label in [
    (20, '#ef4444', 'Critical 20%'),
    (35, '#f59e0b', 'Warning 35%'),
]:
    fig_forecast.add_hline(
        y=thresh, row=2, col=1,
        line_dash='dash', line_color=color, line_width=1,
        annotation_text=label,
        annotation_font_color=color,
        annotation_font_size=10,
    )

fig_forecast.update_layout(
    height=500,
    paper_bgcolor='#0f1117',
    plot_bgcolor='#0f1117',
    font=dict(color='#7c8db5'),
    legend=dict(
        orientation='h', y=1.02,
        bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e2e8f0'),
    ),
    margin=dict(t=40, b=20, l=20, r=20),
    hovermode='x unified',
)
fig_forecast.update_xaxes(gridcolor='#1a1d2e')
fig_forecast.update_yaxes(gridcolor='#1a1d2e')
fig_forecast.update_yaxes(title_text="kW", row=1, col=1,
                           title_font_color='#7c8db5')
fig_forecast.update_yaxes(title_text="%", row=2, col=1,
                           title_font_color='#7c8db5', range=[0, 100])

st.plotly_chart(fig_forecast, use_container_width=True)


# ════════════════════════════════════════════
# CHART 3 — MODEL ACCURACY (backtest)
# ════════════════════════════════════════════

st.markdown('<div class="section-header">Model Accuracy — Backtest (Last 15% of Data)</div>',
            unsafe_allow_html=True)

col_left, col_right = st.columns([2, 1])

with col_left:
    backtest_hours = min(168, len(y_test))
    fig_bt = go.Figure()
    fig_bt.add_trace(go.Scatter(
        y=y_test.values[:backtest_hours],
        name='Actual load',
        line=dict(color='#ef4444', width=1.5),
    ))
    fig_bt.add_trace(go.Scatter(
        y=test_preds[:backtest_hours],
        name='AI prediction',
        line=dict(color='#3b82f6', width=1.5, dash='dot'),
    ))
    fig_bt.update_layout(
        height=260,
        paper_bgcolor='#0f1117',
        plot_bgcolor='#0f1117',
        font=dict(color='#7c8db5'),
        title=dict(
            text='Actual vs Predicted — 1 Week Sample',
            font=dict(color='#e2e8f0', size=13)
        ),
        legend=dict(
            orientation='h', y=1.02,
            bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e2e8f0')
        ),
        xaxis=dict(gridcolor='#1a1d2e', title='Hours'),
        yaxis=dict(gridcolor='#1a1d2e', title='kW'),
        margin=dict(t=40, b=20, l=20, r=20),
    )
    st.plotly_chart(fig_bt, use_container_width=True)

with col_right:
    st.markdown("**Model Performance**")
    st.metric("MAE",  f"{mae:.1f} kW",   help="Mean Absolute Error — avg kW off")
    st.metric("MAPE", f"{mape:.1f}%",    help="Mean Absolute % Error")
    accuracy = max(0, 100 - mape)
    st.metric("Accuracy", f"{accuracy:.1f}%")
    st.progress(min(1.0, accuracy / 100))

    st.markdown("**Top Features**")
    top_features = importance.head(5)
    for feat, score in top_features.items():
        short = feat.replace('load_', '').replace('_h', 'h').replace('_', ' ')
        st.markdown(
            f"<div style='font-size:11px;color:#7c8db5;margin-bottom:4px'>"
            f"{short}<br>"
            f"<div style='height:4px;background:#2d3561;border-radius:2px;margin-top:2px'>"
            f"<div style='width:{score*100:.0f}%;height:4px;"
            f"background:#3b82f6;border-radius:2px'></div></div></div>",
            unsafe_allow_html=True
        )


# ════════════════════════════════════════════
# TARIFF SAVINGS CALCULATOR
# ════════════════════════════════════════════

st.markdown('<div class="section-header">India Tariff Savings Calculator</div>',
            unsafe_allow_html=True)

col_s1, col_s2, col_s3 = st.columns(3)

# Calculate savings from tariff arbitrage
cheap_hours_energy  = forecast_df.loc[
    forecast_df.index.hour.isin(range(10, 16)), 'forecast_kw'
].sum() * 0.5  # kWh in cheap hours (0.5h intervals approx)

peak_hours_energy   = forecast_df.loc[
    forecast_df.index.hour.isin(range(18, 23)), 'forecast_kw'
].sum() * 0.5

arbitrage_saving    = (peak_hours_energy - cheap_hours_energy) * (peak_rate - cheap) / 30

demand_charge_kwh   = forecast_df['forecast_kw'].max()
demand_saving       = demand_charge_kwh * 0.15 * 320 / 30  # 15% peak shaving

monthly_saving      = (arbitrage_saving + demand_saving) * 30
annual_saving       = monthly_saving * 12

with col_s1:
    st.metric("Daily Tariff Saving",   f"₹{arbitrage_saving + demand_saving:,.0f}")
with col_s2:
    st.metric("Monthly Saving",        f"₹{monthly_saving:,.0f}")
with col_s3:
    st.metric("Annual Saving",         f"₹{annual_saving:,.0f}",
              delta=f"vs ₹{min(60000, annual_saving * 0.05):,.0f}/yr software cost")

st.caption(
    f"Based on {state_tariff} tariff: ₹{cheap}/kWh cheap · "
    f"₹{normal}/kWh normal · ₹{peak_rate}/kWh peak. "
    f"Savings from ToD arbitrage + demand charge shaving."
)
