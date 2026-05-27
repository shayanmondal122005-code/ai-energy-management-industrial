# battery_tracker.py
# Pure physics model for battery State of Charge
# No ML needed — this is your physics degree in code
# EDIT: update BATTERY_SPECS to match each customer's battery

import numpy as np
import pandas as pd

# ── EDIT THESE for each customer site ──
BATTERY_SPECS = {
    'capacity_kwh'     : 500,    # EDIT: total battery capacity in kWh
    'max_charge_kw'    : 150,    # EDIT: max charging rate in kW
    'max_discharge_kw' : 200,    # EDIT: max discharging rate in kW
    'charge_efficiency': 0.95,   # EDIT: charging efficiency (0.92-0.97)
    'discharge_efficiency': 0.95,# EDIT: discharging efficiency
    'min_soc'          : 0.10,   # EDIT: never discharge below 10% (protects battery)
    'max_soc'          : 0.95,   # EDIT: never charge above 95% (protects battery)
    'initial_soc'      : 0.80,   # EDIT: starting charge when you boot the system
    'degradation_rate' : 0.00005,# battery loses this fraction of capacity per cycle
    'temp_coefficient' : 0.005,  # capacity reduces by 0.5% per °C above 25°C
}


class BatteryTracker:
    """
    Physics-based battery state tracker.
    
    Runs every minute/15-minutes and maintains accurate SoC.
    Uses Coulomb counting (integrating power over time).
    """
    
    def __init__(self, specs=BATTERY_SPECS):
        self.specs        = specs
        self.soc          = specs['initial_soc']      # current SoC (0-1)
        self.capacity_kwh = specs['capacity_kwh']      # current usable capacity
        self.cycles       = 0                          # full charge cycles completed
        self.history      = []                         # log of all states
    
    def update(self, net_power_kw, delta_hours=0.25, temp_c=25):
        """
        Update SoC based on net power flow over a time step.
        
        Args:
            net_power_kw : solar_kw - load_kw (positive=charging, negative=discharging)
            delta_hours  : time step size in hours (0.25 = 15 min intervals)
            temp_c       : current temperature (affects capacity)
        
        Returns: current SoC as percentage
        
        EDIT: change delta_hours to match your data frequency
        """
        # Temperature correction — battery holds less charge when hot
        # Arrhenius-based: capacity reduces with temperature
        temp_factor = 1 - self.specs['temp_coefficient'] * max(0, temp_c - 25)
        effective_capacity = self.capacity_kwh * temp_factor
        
        # Apply charge or discharge with efficiency losses
        if net_power_kw > 0:
            # Charging — apply charge efficiency (some energy lost as heat)
            actual_power = min(net_power_kw, self.specs['max_charge_kw'])
            delta_soc = (actual_power * self.specs['charge_efficiency'] 
                        * delta_hours) / effective_capacity
        else:
            # Discharging — apply discharge efficiency
            actual_power = max(net_power_kw, -self.specs['max_discharge_kw'])
            delta_soc = (actual_power / self.specs['discharge_efficiency'] 
                        * delta_hours) / effective_capacity
        
        # Update SoC and clamp to safe limits
        new_soc = self.soc + delta_soc
        self.soc = np.clip(new_soc, self.specs['min_soc'], self.specs['max_soc'])
        
        # Track degradation — battery slowly loses capacity over cycles
        if delta_soc < 0:  # only count discharge for cycle counting
            self.cycles += abs(delta_soc) / 2  # full cycle = discharge 100%
            self.capacity_kwh *= (1 - self.specs['degradation_rate'] * abs(delta_soc))
        
        # Log this state
        self.history.append({
            'soc_pct'           : round(self.soc * 100, 2),
            'capacity_kwh'      : round(self.capacity_kwh, 1),
            'net_power_kw'      : round(net_power_kw, 1),
            'temp_c'            : temp_c,
            'state_of_health'   : round(self.capacity_kwh / BATTERY_SPECS['capacity_kwh'] * 100, 1),
        })
        
        return self.soc * 100  # return as percentage
    
    def hours_remaining(self, load_kw, solar_kw):
        """
        How many hours until battery is empty at current power flow?
        This is the key number shown on your dashboard.
        """
        net_power = solar_kw - load_kw
        if net_power >= 0:
            return float('inf')  # charging — never empty
        
        usable_energy = (self.soc - self.specs['min_soc']) * self.capacity_kwh
        drain_rate     = abs(net_power) / self.specs['discharge_efficiency']
        
        if drain_rate == 0:
            return float('inf')
        
        hours = usable_energy / drain_rate
        return round(hours, 1)
    
    def soh_pct(self):
        """State of Health — how degraded is the battery vs brand new"""
        return round(self.capacity_kwh / BATTERY_SPECS['capacity_kwh'] * 100, 1)
    
    def simulate_future(self, forecast_load_kw, forecast_solar_kw, 
                        delta_hours=1.0, temp_c=30):
        """
        Simulate SoC over the next N hours given forecasted load and solar.
        Used by the brain to decide actions in advance.
        
        Returns: list of future SoC values (one per hour)
        """
        sim_soc   = self.soc
        sim_cap   = self.capacity_kwh
        soc_trace = [round(sim_soc * 100, 1)]
        
        for load, solar in zip(forecast_load_kw, forecast_solar_kw):
            net = solar - load
            
            if net > 0:
                delta = (min(net, self.specs['max_charge_kw']) 
                        * self.specs['charge_efficiency'] 
                        * delta_hours) / sim_cap
            else:
                delta = (max(net, -self.specs['max_discharge_kw']) 
                        / self.specs['discharge_efficiency'] 
                        * delta_hours) / sim_cap
            
            sim_soc = np.clip(sim_soc + delta, 
                              self.specs['min_soc'], 
                              self.specs['max_soc'])
            soc_trace.append(round(sim_soc * 100, 1))
        
        return soc_trace  # list of SoC% values for next N hours
    