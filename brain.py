# brain.py
# The decision engine — watches forecasts and decides what to do
# EDIT: tune the thresholds to match your customer's priorities
# This is the most important file — it IS your product's intelligence

import pandas as pd
from battery_tracker import BatteryTracker

# ── EDIT THESE THRESHOLDS ──
RULES = {
    'soc_critical'       : 20,   # % — below this = emergency. Alert immediately
    'soc_warning'        : 35,   # % — below this = warning. Plan action
    'soc_target_min'     : 50,   # % — try to always stay above this
    'soc_target_max'     : 90,   # % — don't charge above this unnecessarily
    'hours_warning'      : 3,    # hours remaining before warning alert
    'hours_critical'     : 1,    # hours remaining before critical alert
    'peak_demand_kw'     : 350,  # kW — above this = demand charge triggered
    'tod_cheap_hours'    : list(range(10, 16)),   # 10am-4pm cheap rate
    'tod_peak_hours'     : list(range(18, 23)),   # 6pm-11pm peak rate
    'precharge_threshold': 60,   # % — pre-charge battery to this level before peak
}

class MicrogridBrain:
    """
    The central decision-making engine. Runs every 15 minutes in production.
    It watches 5 things:
    1. Current SoC
    2. Forecast load (next 24h)
    3. Forecast solar (next 24h)
    4. Simulated future SoC (from battery tracker)
    5. Current tariff rate (cheap/peak/offpeak)
    
    And makes 4 types of decisions:
    A. CHARGE  — import from grid to fill battery
    B. DISCHARGE — use battery, reduce grid import
    C. ALERT   — send notification to facility manager
    D. HOLD    — do nothing, system is fine
    """
    def __init__(self, battery: BatteryTracker, rules=RULES):
        self.battery  = battery
        self.rules    = rules
        self.alerts   = []
        self.decisions= []

    def run(self, current_hour, current_load_kw, current_solar_kw, forecast_load, forecast_solar, temp_c=30):
        """
        Main brain loop — call this every 15 minutes.
        Args:
            current_hour   : int 0-23, current hour of day
            current_load_kw: float, current electricity demand
            current_solar_kw: float, current solar output
            forecast_load  : list of 24 hourly load forecasts (kW)
            forecast_solar : list of 24 hourly solar forecasts (kW)
            temp_c         : current temperature
        Returns:
            dict with decision + reasoning + alerts
        """
        # Step 1: update battery with current real data
        current_soc = self.battery.update(
            net_power_kw=current_solar_kw - current_load_kw,
            delta_hours=0.25,  # 15-minute interval
            temp_c=temp_c
        )
        
        # Step 2: simulate battery over next 24 hours
        future_soc = self.battery.simulate_future(
            forecast_load_kw=forecast_load,
            forecast_solar_kw=forecast_solar,
            temp_c=temp_c
        )
        
        # Step 3: gather all the facts
        hours_left   = self.battery.hours_remaining(current_load_kw, current_solar_kw)
        min_future_soc = min(future_soc)
        when_lowest  = future_soc.index(min_future_soc)
        
        is_cheap_now = current_hour in self.rules['tod_cheap_hours']
        is_peak_now  = current_hour in self.rules['tod_peak_hours']
        
        # Check if peak hours are approaching in the next 4 hours
        peak_coming  = any(h % 24 in self.rules['tod_peak_hours'] for h in range(current_hour, current_hour + 4))
        
        alerts  = []
        actions = []

        # ── SYSTEM HEALTH & EMERGENCY RULES ──
        
        # RULE 1: Emergency — battery critically low right now
        if current_soc < self.rules['soc_critical']:
            alerts.append({
                'severity': 'CRITICAL', 
                'message' : f"Battery at {current_soc:.0f}% — CRITICAL. Grid import required immediately to prevent shutdown.", 
                'action'  : 'CHARGE_NOW'
            })
            actions.append('EMERGENCY_CHARGE')
            
        # RULE 2: Battery will get critically low in next 24h
        elif min_future_soc < self.rules['soc_critical']:
            alerts.append({
                'severity': 'WARNING', 
                'message' : f"Battery forecast to reach {min_future_soc:.0f}% in {when_lowest} hours. Consider grid charging now.", 
                'action'  : 'PLAN_CHARGE'
            })

        # ── TARIFF & ECONOMIC MANAGEMENT RULES ──
        # Fixed: Evaluated independently so rules don't block each other
        
        # RULE 3: Cheap tariff hours — charge battery if below target
        if is_cheap_now and current_soc < self.rules['precharge_threshold'] and not is_peak_now:
            actions.append('CHARGE_FROM_GRID')
            alerts.append({
                'severity': 'INFO', 
                'message' : f"Off-peak rate active. Charging battery from {current_soc:.0f}% to {self.rules['precharge_threshold']}% now. Saves cost vs peak-hour import.", 
                'action'  : 'CHARGING'
            })
            
        # RULE 4: Peak hours approaching — pre-charge if not ready
        if peak_coming and current_soc < self.rules['precharge_threshold'] and is_cheap_now and not is_peak_now:
            # Fixed: Safely compute remaining hours even across day boundaries
            hours_until_peak = (self.rules['tod_peak_hours'][0] - current_hour) % 24
            actions.append('PRECHARGE_FOR_PEAK')
            alerts.append({
                'severity': 'INFO', 
                'message' : f"Evening peak in {hours_until_peak}h. Pre-charging battery to {self.rules['precharge_threshold']}% at cheap rate now.", 
                'action'  : 'PRECHARGING'
            })
            
        # RULE 5: During peak hours — discharge battery to avoid grid peak
        if is_peak_now and current_soc > (self.rules['soc_critical'] + 10):
            actions.append('DISCHARGE_TO_SHAVE_PEAK')
            alerts.append({
                'severity': 'INFO', 
                'message' : f"Peak tariff active. Discharging battery to cover {current_load_kw:.0f}kW load. Avoiding grid import.", 
                'action'  : 'DISCHARGING'
            })

        # ── RULE 6: High demand — about to trigger demand charge ──
        if current_load_kw > self.rules['peak_demand_kw']:
            shave_needed = current_load_kw - self.rules['peak_demand_kw']
            if current_soc > (self.rules['soc_critical'] + 5):
                actions.append('DEMAND_SHAVE')
                alerts.append({
                    'severity': 'WARNING', 
                    'message' : f"Demand at {current_load_kw:.0f}kW — above {self.rules['peak_demand_kw']}kW threshold. Discharging {shave_needed:.0f}kW from battery to prevent demand charge spike.", 
                    'action'  : 'SHAVING'
                })

        # ── Default: system stable, no action needed ──
        if not actions:
            actions.append('HOLD')

        # Package the full decision
        decision = {
            'timestamp'      : pd.Timestamp.now(), # Note: Ensure host machine timezone is aligned
            'current_soc_pct': round(current_soc, 1),
            'hours_remaining': hours_left,
            'min_future_soc' : round(min_future_soc, 1),
            'lowest_in_hrs'  : when_lowest,
            'soh_pct'        : self.battery.soh_pct(),
            'actions'        : actions,
            'alerts'         : alerts,
            'is_cheap_tariff': is_cheap_now,
            'is_peak_tariff' : is_peak_now,
            'future_soc_trace': future_soc,  # full 24h SoC curve
        }
        
        self.decisions.append(decision)
        return decision

    def print_status(self, decision):
        """Pretty print current system status — for terminal testing"""
        print("\n" + "="*50)
        print(f"MICROGRID BRAIN STATUS — {decision['timestamp'].strftime('%H:%M')}")
        print("="*50)
        print(f"Battery SoC   : {decision['current_soc_pct']}%")
        print(f"Hours left    : {decision['hours_remaining']}h")
        print(f"State of Health: {decision['soh_pct']}%")
        print(f"Tariff now    : {'CHEAP ✓' if decision['is_cheap_tariff'] else 'PEAK ⚠' if decision['is_peak_tariff'] else 'NORMAL'}")
        print(f"Actions       : {', '.join(decision['actions'])}")
        print(f"\nAlerts ({len(decision['alerts'])}):")
        for a in decision['alerts']:
            icon = '🔴' if a['severity']=='CRITICAL' else '🟡' if a['severity']=='WARNING' else '🔵'
            print(f"  {icon} [{a['severity']}] {a['message']}")
        print("="*50)
        
