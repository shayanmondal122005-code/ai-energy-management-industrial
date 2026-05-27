# dashboard.py
# Run with: streamlit run dashboard.py
# EDIT: connect to real data by replacing the sample_data() function

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from battery_tracker import BatteryTracker, BATTERY_SPECS
from brain import MicrogridBrain, RULES

st.set_page_config(
    page_title="MicroGrid AI — Kolkata",
    layout="wide",
    page_icon="⚡"
)

# ── EDIT: replace this with real data loading ──
@st.cache_data(ttl=300)  # refresh every 5 minutes
def get_live_data():
    """
    EDIT THIS FUNCTION to load real data from your IoT gateway.
    For now it generates realistic sample data.
    """
    hours = pd.date_range(end=pd.Timestamp.now(), periods=48, freq='1h')
    np.random.seed(42)
    
    # Simulate realistic hospital load (peaks morning and evening)
    load = [280 + 80*np.sin((h.hour-8)*np.pi/12) + np.random.normal(0,15)
            for h in hours]
    # Simulate solar (zero at night, peaks at noon)
    solar = [max(0, 180*np.sin((h.hour-6)*np.pi/12) + np.random.normal(0,10))
             for h in hours]
    
    return pd.DataFrame({
        'timestamp': hours,
        'load_kw'  : np.clip(load, 180, 450),
        'solar_kw' : solar,
        'temp_c'   : [28 + np.random.normal(0,2) for _ in hours],
    }).set_index('timestamp')


def run_brain_on_data(df):
    """Run the brain on historical data to get status and decisions"""
    battery = BatteryTracker(BATTERY_SPECS)
    brain   = MicrogridBrain(battery, RULES)
    
    # Use last 24h for forecast (simplified)
    forecast_load  = df['load_kw'].tail(24).tolist()
    forecast_solar = df['solar_kw'].tail(24).tolist()
    current        = df.iloc[-1]
    
    decision = brain.run(
        current_hour      = df.index[-1].hour,
        current_load_kw   = current['load_kw'],
        current_solar_kw  = current['solar_kw'],
        forecast_load     = forecast_load,
        forecast_solar    = forecast_solar,
        temp_c            = current['temp_c'],
    )
    return decision, battery


# ── MAIN DASHBOARD ──
st.title("⚡ MicroGrid AI Dashboard")
st.caption("Real-time energy intelligence · Kolkata")

df      = get_live_data()
decision, battery = run_brain_on_data(df)
current = df.iloc[-1]

# ── Row 1: Key metrics ──
col1, col2, col3, col4, col5 = st.columns(5)

soc = decision['current_soc_pct']
col1.metric("Battery SoC",
            f"{soc:.0f}%",
            delta=f"{soc-70:.0f}% vs target",
            delta_color="normal")

col2.metric("Current Load",     f"{current['load_kw']:.0f} kW")
col3.metric("Solar Output",     f"{current['solar_kw']:.0f} kW")
col4.metric("Hours Remaining",  f"{decision['hours_remaining']}h",
            delta_color="inverse")
col5.metric("State of Health",  f"{decision['soh_pct']}%")

st.divider()

# ── Row 2: Alerts ──
if decision['alerts']:
    for alert in decision['alerts']:
        if alert['severity'] == 'CRITICAL':
            st.error(f"🔴 CRITICAL: {alert['message']}")
        elif alert['severity'] == 'WARNING':
            st.warning(f"🟡 WARNING: {alert['message']}")
        else:
            st.info(f"🔵 {alert['message']}")

# ── Row 3: Charts ──
col_left, col_right = st.columns(2)

with col_left:
    # Power balance chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, y=df['load_kw'],
        name='Demand (kW)', line=dict(color='#ef4444', width=2)
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df['solar_kw'],
        name='Solar (kW)', line=dict(color='#f59e0b', width=2),
        fill='tozeroy', fillcolor='rgba(245,158,11,0.1)'
    ))
    fig.update_layout(
        title='Power Balance — Last 48 Hours',
        height=300, margin=dict(t=40,b=20,l=20,r=20),
        legend=dict(orientation='h', y=-0.2)
    )
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    # Battery SoC forecast
    future_soc = decision['future_soc_trace']
    hours_ahead = [f"+{i}h" for i in range(len(future_soc))]
    
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=hours_ahead, y=future_soc,
        name='Predicted SoC (%)',
        line=dict(color='#10b981', width=2),
        fill='tozeroy', fillcolor='rgba(16,185,129,0.1)'
    ))
    fig2.add_hline(y=RULES['soc_critical'], line_dash="dash",
                   line_color="#ef4444",
                   annotation_text=f"Critical {RULES['soc_critical']}%")
    fig2.add_hline(y=RULES['soc_warning'], line_dash="dash",
                   line_color="#f59e0b",
                   annotation_text=f"Warning {RULES['soc_warning']}%")
    fig2.update_layout(
        title='Battery SoC Forecast — Next 24 Hours',
        height=300, margin=dict(t=40,b=20,l=20,r=20),
        yaxis=dict(range=[0,100])
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Row 4: Brain decision log ──
st.subheader("Brain Decision")
st.write(f"**Actions taken:** {', '.join(decision['actions'])}")
st.write(f"**Min forecast SoC:** {decision['min_future_soc']}% (in {decision['lowest_in_hrs']} hours)")
st.write(f"**Tariff now:** {'🟢 Cheap rate' if decision['is_cheap_tariff'] else '🔴 Peak rate' if decision['is_peak_tariff'] else '⚪ Normal rate'}")