# data_loader.py
# This block loads and prepares your energy data for all models
# EDIT: change the file paths to match your actual data files

import pandas as pd
import numpy as np

def load_energy_data(filepath):
    """
    Load raw energy data from a CSV file.
    
    Expected CSV columns (rename yours to match):
        timestamp  : datetime string  e.g. "2024-01-01 08:00:00"
        load_kw    : electricity demand in kilowatts
        solar_kw   : solar output in kilowatts (0 if not available yet)
        battery_soc: battery state of charge 0-100% (0 if not available)
        temp_c     : outdoor temperature in Celsius
    
    EDIT THIS: change column names below to match your real CSV
    """
    df = pd.read_csv(filepath)
    
    # ── EDIT these names to match your CSV column headers ──
    df = df.rename(columns={
        'timestamp'  : 'timestamp',   # your time column name
        'load_kw'    : 'load_kw',     # your demand/load column
        'solar_kw'   : 'solar_kw',    # your solar output column
        'battery_soc': 'battery_soc', # your battery % column
        'temp_c'     : 'temp_c',      # your temperature column
    })
    
    # Convert timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    df = df.set_index('timestamp')
    
    # Fill missing values with forward fill (use last known value)
    df = df.ffill()
    
    print(f"Loaded {len(df)} rows from {df.index[0]} to {df.index[-1]}")
    return df


def add_time_features(df):
    """
    Add time-based features that help XGBoost learn patterns.
    These are the most powerful features for energy forecasting.
    
    EDIT: add more features if you have extra data (humidity, holidays etc.)
    """
    df = df.copy()
    
    df['hour']       = df.index.hour          # 0-23: what hour of day
    df['dayofweek']  = df.index.dayofweek     # 0=Mon, 6=Sun
    df['month']      = df.index.month         # 1-12
    df['quarter']    = df.index.quarter       # 1-4
    df['is_weekend'] = (df.index.dayofweek >= 5).astype(int)  # 1 if weekend
    df['is_morning_peak']  = df['hour'].between(8, 11).astype(int)
    df['is_evening_peak']  = df['hour'].between(18, 22).astype(int)
    df['is_tod_cheap']     = df['hour'].between(10, 16).astype(int) # ToD cheap hours
    
    # Lag features — what was load 1 hour ago, 24 hours ago, 1 week ago
    # These are crucial: today at 9am usually looks like yesterday at 9am
    df['load_lag_1h']  = df['load_kw'].shift(1)   # 1 hour ago
    df['load_lag_24h'] = df['load_kw'].shift(24)  # same time yesterday
    df['load_lag_168h']= df['load_kw'].shift(168) # same time last week
    
    # Rolling averages — smoothed recent history
    df['load_rolling_3h']  = df['load_kw'].rolling(3).mean()
    df['load_rolling_24h'] = df['load_kw'].rolling(24).mean()
    
    df = df.dropna()  # remove rows where lag features are NaN
    return df


# ── TEST THIS BLOCK ──
# Uncomment and run to test with sample data
# if __name__ == "__main__":
#     df = load_energy_data('your_data.csv')
#     df = add_time_features(df)
#     print(df.head())
#     print("Features:", df.columns.tolist())