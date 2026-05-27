# run.py
# ENTRY POINT — run this file to start the full system
# python run.py

from data_loader import load_energy_data, add_time_features
from load_forecaster import train_load_model, predict_next_24h, save_model
from battery_tracker import BatteryTracker, BATTERY_SPECS
from brain import MicrogridBrain, RULES
import pandas as pd

print("=== MICROGRID AI SYSTEM STARTING ===\n")

# Step 1: Load your data
# EDIT: replace 'sample_data.csv' with your actual file
print("Step 1: Loading data...")
# df = load_energy_data('sample_data.csv')     # use this with real data
# For testing without real data — generate sample data
import numpy as np
hours = pd.date_range('2024-01-01', periods=2000, freq='1h')
df = pd.DataFrame({
    'load_kw'    : 300 + 80*np.sin(np.arange(2000)*0.26) + np.random.normal(0,20,2000),
    'solar_kw'   : [max(0, 180*np.sin((h.hour-6)*np.pi/12)) for h in hours],
    'battery_soc': 70 + np.random.normal(0,5,2000),
    'temp_c'     : 28 + np.random.normal(0,3,2000),
}, index=hours)

df = add_time_features(df)
print(f"  Loaded {len(df)} rows of data\n")

# Step 2: Train load forecast model
print("Step 2: Training load forecast model...")
model, mae, mape, _, _ = train_load_model(df)
save_model(model)
print(f"  Done. MAE={mae:.1f}kW, MAPE={mape:.1f}%\n")

# Step 3: Generate 24h forecast
print("Step 3: Generating 24-hour forecast...")
forecast = predict_next_24h(model, df.tail(200))
print(forecast)
print()

# Step 4: Run the brain on current state
print("Step 4: Running the brain...")
battery = BatteryTracker(BATTERY_SPECS)
brain   = MicrogridBrain(battery, RULES)

decision = brain.run(
    current_hour      = pd.Timestamp.now().hour,
    current_load_kw   = df['load_kw'].iloc[-1],
    current_solar_kw  = df['solar_kw'].iloc[-1],
    forecast_load     = forecast['forecast_kw'].tolist(),
    forecast_solar    = [max(0, 180*np.sin((h.hour-6)*np.pi/12))
                        for h in forecast.index],
    temp_c            = df['temp_c'].iloc[-1]
)

brain.print_status(decision)

print("\n=== LAUNCH DASHBOARD ===")
print("Run this command in your terminal:")
print("  streamlit run dashboard.py")