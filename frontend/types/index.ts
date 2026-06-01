// Central TypeScript types for MicroGrid AI frontend

export type UserRole = "super_admin" | "tenant_admin" | "operator" | "viewer";

export type GridMode =
  | "GRID_CONNECTED"
  | "ISLAND"
  | "TRANSITION"
  | "EMERGENCY"
  | "MAINTENANCE";

export type AlertSeverity = "critical" | "warning" | "info" | "ok";

export type LoadPriority = 1 | 2 | 3 | 4 | 5;

export interface User {
  user_id: string;
  tenant_id: string;
  email: string;
  role: UserRole;
  full_name?: string;
}

export interface Facility {
  id: string;
  tenant_id: string;
  name: string;
  city: string;
  lat: number;
  lon: number;
  state_tariff: string;
  battery_kwh: number;
  solar_kw: number;
  avg_load_kw: number;
  is_active: boolean;
}

export interface LiveReading {
  status: string;
  timestamp: string | null;
  load_kw: number;
  solar_kw: number;
  battery_soc: number;
  battery_temp: number;
  grid_kw: number;
  net_kw: number;
  source: string;
}

export interface Alert {
  id: string;
  facility_id: string;
  severity: AlertSeverity;
  type: string;
  message: string;
  value: number | null;
  threshold: number | null;
  whatsapp_sent: boolean;
  acknowledged_at: string | null;
  created_at: string;
}

export interface GridState {
  facility_id: string;
  mode: GridMode;
  main_breaker: boolean;
  battery_command: "CHARGE" | "DISCHARGE" | "HOLD";
  grid_voltage_v: number | null;
  grid_frequency_hz: number | null;
  last_mode_change: string;
}

export interface LoadConfig {
  id: string;
  load_id: string;
  name: string;
  priority: LoadPriority;
  rated_kw: number;
  contactor_id: string | null;
  is_on: boolean;
  shed_order: number | null;
}

export interface IndiaTariff {
  state: string;
  cheap: number;
  normal: number;
  peak: number;
  demand_per_kw: number;
  cheap_hours: number[];
  peak_hours: number[];
}

// India tariff constants — same as backend
export const INDIA_TARIFFS: Record<string, IndiaTariff> = {
  "West Bengal - CESC": {
    state: "West Bengal - CESC",
    cheap: 4.20, normal: 6.10, peak: 7.85, demand_per_kw: 320,
    cheap_hours: [10,11,12,13,14,15], peak_hours: [18,19,20,21,22],
  },
  "Maharashtra - MSEDCL": {
    state: "Maharashtra - MSEDCL",
    cheap: 3.80, normal: 5.90, peak: 8.20, demand_per_kw: 280,
    cheap_hours: [10,11,12,13,14,15], peak_hours: [18,19,20,21],
  },
  "Tamil Nadu - TANGEDCO": {
    state: "Tamil Nadu - TANGEDCO",
    cheap: 4.50, normal: 6.40, peak: 8.10, demand_per_kw: 350,
    cheap_hours: [10,11,12,13,14,15,16], peak_hours: [18,19,20,21,22],
  },
  "Karnataka - BESCOM": {
    state: "Karnataka - BESCOM",
    cheap: 4.10, normal: 6.00, peak: 7.70, demand_per_kw: 295,
    cheap_hours: [10,11,12,13,14,15], peak_hours: [18,19,20,21],
  },
  "Delhi - BSES/TPDDL": {
    state: "Delhi - BSES/TPDDL",
    cheap: 3.90, normal: 5.80, peak: 7.50, demand_per_kw: 260,
    cheap_hours: [10,11,12,13,14,15], peak_hours: [17,18,19,20,21],
  },
};
