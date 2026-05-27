# solar_forecaster.py
# Uses PVLib physics + XGBoost to predict solar output 24h ahead
# EDIT: update SYSTEM settings to match your customer's actual solar installation

import pvlib
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

# ── EDIT THESE for each customer site ──
SYSTEM = {
    'latitude'        : 22.57,    # EDIT: customer's latitude
    'longitude'       : 88.36,    # EDIT: customer's longitude
    'altitude_m'      : 9,        # EDIT: site altitude in metres
    'timezone'        : 'Asia/Kolkata',
    'panel_capacity_kw': 200,     # EDIT: total solar array size in kW
    'panel_efficiency' : 0.20,    # EDIT: panel efficiency (0.18-0.22 typical)
    'temp_coefficient' : -0.004,  # EDIT: power drop per °C above 25°C
    'system_losses'    : 0.14,    # EDIT: cable, inverter, dust losses (~14%)
}


def get_clearsky_solar(start_date, periods_hours=24):
    """
    Get theoretical maximum solar output if sky is perfectly clear.
    This is the physics baseline — actual output is always less than this.
    """
    location = pvlib.location.Location(
        latitude  = SYSTEM['latitude'],
        longitude = SYSTEM['longitude'],
        tz        = SYSTEM['timezone'],
        altitude  = SYSTEM['altitude_m'],
    )
    
    times = pd.date_range(
        start=start_date,
        periods=periods_hours,
        freq='1h',
        tz=SYSTEM['timezone']
    )
    
    # Get clear-sky irradiance (GHI, DNI, DHI in W/m²)
    clearsky = location.get_clearsky(times)
    
    # Convert irradiance to actual power output
    # P = GHI × panel_area × efficiency × (1 - temp_coefficient × ΔT)
    # Simplified: use GHI directly with system efficiency
    clearsky['solar_kw'] = (
        clearsky['ghi'] / 1000   # W/m² → kW/m²
        * SYSTEM['panel_capacity_kw']
        * SYSTEM['panel_efficiency']
        * (1 - SYSTEM['system_losses'])
    ).clip(lower=0)
    
    return clearsky[['ghi', 'dni', 'dhi', 'solar_kw']]


def add_solar_features(df, clearsky_df):
    """
    Merge weather + clearsky + actual solar to create XGBoost features.
    EDIT: add cloud cover or humidity columns if you have weather API data
    """
    df = df.copy()
    
    # Add clearsky as features (the theoretical maximum)
    df['clearsky_ghi']   = clearsky_df['ghi'].reindex(df.index, method='nearest')
    df['clearsky_solar'] = clearsky_df['solar_kw'].reindex(df.index, method='nearest')
    
    # Cloud factor: actual vs theoretical (0=cloudy, 1=clear sky)
    df['cloud_factor'] = (df['solar_kw'] / df['clearsky_solar'].replace(0, 0.001)).clip(0, 1)
    
    # Time features (solar is very time-dependent)
    df['hour']          = df.index.hour
    df['month']         = df.index.month
    df['solar_lag_24h'] = df['solar_kw'].shift(24)   # same time yesterday
    df['solar_lag_48h'] = df['solar_kw'].shift(48)   # same time 2 days ago
    
    return df.dropna()


def train_solar_model(df):
    """
    Train XGBoost to predict actual solar output from clearsky + history.
    The model learns how clouds reduce output vs the theoretical maximum.
    """
    # ── EDIT: add/remove features here ──
    solar_features = [
        'hour', 'month',
        'clearsky_ghi',         # theoretical irradiance
        'clearsky_solar',       # theoretical output
        'solar_lag_24h',        # actual output same time yesterday
        'solar_lag_48h',        # actual output 2 days ago
        'temp_c',               # temperature affects efficiency
    ]
    
    df_clean = df[solar_features + ['solar_kw']].dropna()
    # Only train on daytime hours (solar > 0)
    df_clean = df_clean[df_clean['clearsky_solar'] > 5]
    
    X = df_clean[solar_features]
    y = df_clean['solar_kw']
    
    split_idx = int(len(df_clean) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        random_state=42
    )
    model.fit(X_train, y_train)
    
    preds = model.predict(X_test).clip(0)
    mae   = mean_absolute_error(y_test, preds)
    print(f"Solar model MAE: {mae:.1f} kW")
    
    return model


def forecast_solar_24h(solar_model, tomorrow_date, last_known_temp=30):
    """
    Predict solar output for the next 24 hours.
    Returns hourly kW forecast.
    """
    clearsky = get_clearsky_solar(tomorrow_date, periods_hours=24)
    
    rows = []
    for i, (ts, row) in enumerate(clearsky.iterrows()):
        rows.append({
            'hour'            : ts.hour,
            'month'           : ts.month,
            'clearsky_ghi'    : row['ghi'],
            'clearsky_solar'  : row['solar_kw'],
            'solar_lag_24h'   : row['solar_kw'] * 0.85,  # assume slight cloud
            'solar_lag_48h'   : row['solar_kw'] * 0.85,
            'temp_c'          : last_known_temp,
        })
    
    X = pd.DataFrame(rows)
    predictions = solar_model.predict(X).clip(0)
    
    clearsky['forecast_solar_kw'] = predictions
    return clearsky[['forecast_solar_kw']]