# load_forecaster.py
# XGBoost model that predicts electricity demand 24 hours ahead
# EDIT: tune the parameters in XGBOOST_PARAMS to improve accuracy

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
import joblib  # for saving/loading the model
import matplotlib.pyplot as plt

# ── EDIT THESE PARAMETERS to tune model accuracy ──
XGBOOST_PARAMS = {
    'n_estimators'    : 500,    # number of trees. More = slower but more accurate
    'max_depth'       : 6,      # tree depth. 4-8 is usually best for energy data
    'learning_rate'   : 0.05,   # smaller = more accurate but slower. Try 0.01-0.1
    'subsample'       : 0.8,    # fraction of data per tree. 0.7-0.9 is good
    'colsample_bytree': 0.8,    # fraction of features per tree
    'min_child_weight': 3,      # prevents overfitting. Increase if overfitting
    'random_state'    : 42,     # for reproducibility
    'early_stopping_rounds': 50 # stops if no improvement after 50 rounds
}

# ── EDIT: these are your input features ──
# Add or remove features based on what data you have
FEATURES = [
    'hour', 'dayofweek', 'month', 'quarter',
    'is_weekend', 'is_morning_peak', 'is_evening_peak',
    'load_lag_1h', 'load_lag_24h', 'load_lag_168h',
    'load_rolling_3h', 'load_rolling_24h',
    'temp_c',          # remove this line if you don't have temperature
    'is_tod_cheap',
]

TARGET = 'load_kw'  # what we are predicting


def train_load_model(df):
    """
    Train XGBoost on historical energy data.
    
    Returns: trained model + accuracy metrics
    """
    # Only keep rows where all features exist
    df_clean = df[FEATURES + [TARGET]].dropna()
    
    X = df_clean[FEATURES]
    y = df_clean[TARGET]
    
    # Split: 80% train, 20% test (keep time order — don't shuffle!)
    split_idx = int(len(df_clean) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"Training on {len(X_train)} rows, testing on {len(X_test)} rows")
    
    # Train the model
    model = xgb.XGBRegressor(**XGBOOST_PARAMS)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=100  # prints progress every 100 trees
    )
    
    # Measure accuracy
    predictions = model.predict(X_test)
    mae  = mean_absolute_error(y_test, predictions)
    mape = mean_absolute_percentage_error(y_test, predictions) * 100
    
    print(f"\n── Model Accuracy ──")
    print(f"MAE  : {mae:.1f} kW  (average error in kilowatts)")
    print(f"MAPE : {mape:.1f}%   (average % error)")
    print(f"Goal : MAE < 20 kW, MAPE < 8%")
    
    # Show which features matter most
    importance = pd.Series(
        model.feature_importances_,
        index=FEATURES
    ).sort_values(ascending=False)
    print(f"\n── Top 5 important features ──")
    print(importance.head(5))
    
    return model, mae, mape, predictions, y_test


def predict_next_24h(model, last_known_df):
    """
    Generate a 24-hour ahead demand forecast.
    
    EDIT: pass your most recent 168 rows (1 week) of data as last_known_df
    """
    forecasts = []
    df_temp = last_known_df.copy()
    
    for step in range(24):  # predict each of the next 24 hours
        
        # Build feature row for this future hour
        future_time = df_temp.index[-1] + pd.Timedelta(hours=1)
        
        row = {
            'hour'             : future_time.hour,
            'dayofweek'        : future_time.dayofweek,
            'month'            : future_time.month,
            'quarter'          : future_time.quarter,
            'is_weekend'       : int(future_time.dayofweek >= 5),
            'is_morning_peak'  : int(8 <= future_time.hour <= 11),
            'is_evening_peak'  : int(18 <= future_time.hour <= 22),
            'is_tod_cheap'     : int(10 <= future_time.hour <= 16),
            'load_lag_1h'      : df_temp['load_kw'].iloc[-1],
            'load_lag_24h'     : df_temp['load_kw'].iloc[-24] if len(df_temp) >= 24 else df_temp['load_kw'].mean(),
            'load_lag_168h'    : df_temp['load_kw'].iloc[-168] if len(df_temp) >= 168 else df_temp['load_kw'].mean(),
            'load_rolling_3h'  : df_temp['load_kw'].iloc[-3:].mean(),
            'load_rolling_24h' : df_temp['load_kw'].iloc[-24:].mean(),
            'temp_c'           : df_temp['temp_c'].iloc[-1],  # use last known temp
        }
        
        X_future = pd.DataFrame([row])[FEATURES]
        predicted_load = model.predict(X_future)[0]
        predicted_load = max(0, predicted_load)  # load can't be negative
        
        forecasts.append({
            'timestamp'     : future_time,
            'forecast_kw'   : round(predicted_load, 1),
            'hour_label'    : f"+{step+1}h"
        })
        
        # Add prediction to dataframe so next step can use it as a lag
        new_row = pd.DataFrame({'load_kw': [predicted_load], 'temp_c': [row['temp_c']]},
                                index=[future_time])
        df_temp = pd.concat([df_temp, new_row])
    
    return pd.DataFrame(forecasts).set_index('timestamp')


def save_model(model, path='models/load_model.json'):
    """Save trained model to disk so you don't retrain every time"""
    import os
    os.makedirs('models', exist_ok=True)
    model.save_model(path)
    print(f"Model saved to {path}")


def load_model(path='models/load_model.json'):
    """Load a previously saved model"""
    model = xgb.XGBRegressor()
    model.load_model(path)
    return model


# ── TEST THIS BLOCK ──
# if __name__ == "__main__":
#     from data_loader import load_energy_data, add_time_features
#     df = load_energy_data('your_data.csv')
#     df = add_time_features(df)
#     model, mae, mape, preds, actual = train_load_model(df)
#     save_model(model)
#     forecast = predict_next_24h(model, df.tail(200))
#     print(forecast)