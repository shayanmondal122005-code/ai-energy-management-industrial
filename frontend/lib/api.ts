/**
 * Typed API client for MicroGrid AI backend.
 * All requests include the JWT bearer token from localStorage.
 * Automatically refreshes token on 401.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });

  if (res.status === 401) {
    // Attempt token refresh
    const refreshed = await tryRefresh();
    if (refreshed) {
      return request<T>(path, init);
    }
    window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err.detail ?? "Request failed");
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

async function tryRefresh(): Promise<boolean> {
  const refresh_token = localStorage.getItem("refresh_token");
  if (!refresh_token) return false;
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// ── Auth ─────────────────────────────────────────────────────

export const auth = {
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string; expires_in: number }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) }
    ),
  register: (email: string, password: string, full_name: string, organization: string) =>
    request<{ user_id: string; tenant_id: string; email: string; message: string }>(
      "/auth/register",
      { method: "POST", body: JSON.stringify({ email, password, full_name, organization }) }
    ),
  me: () => request<{ user_id: string; tenant_id: string; email: string; role: string }>("/auth/me"),
};

// ── Facilities ───────────────────────────────────────────────

export type Facility = {
  id: string; tenant_id: string; name: string; city: string;
  lat: number; lon: number; state_tariff: string;
  battery_kwh: number; solar_kw: number; avg_load_kw: number; is_active: boolean;
};

export const facilities = {
  list: () => request<Facility[]>("/facilities/"),
  get: (id: string) => request<Facility>(`/facilities/${id}`),
};

// ── Readings ─────────────────────────────────────────────────

export type LiveReading = {
  status: string; timestamp: string | null;
  load_kw: number; solar_kw: number; battery_soc: number;
  battery_temp: number; grid_kw: number; net_kw: number; source: string;
};

export const readings = {
  live: (facilityId: string) =>
    request<LiveReading>(`/facilities/${facilityId}/live`),
  historyCsv: (facilityId: string, hours = 600) =>
    fetch(`${BASE}/facilities/${facilityId}/history/csv?hours=${hours}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
    }).then((r) => r.text()),
  stats: (facilityId: string) =>
    request<{
      avg_load_kw: number; peak_load_kw: number; avg_solar_kw: number; total_readings: number;
    }>(`/facilities/${facilityId}/stats`),
  solarGeneration: (facilityId: string) =>
    request<{
      facility_id: string; today_kwh: number; month_kwh: number; total_kwh: number;
      peak_today_kw: number; co2_avoided_today_kg: number; updated_at: string;
    }>(`/facilities/${facilityId}/solar/generation`),
};

// ── Bills ────────────────────────────────────────────────────

export type Bill = {
  id: string; period: string; units_kwh: number; peak_demand_kw: number | null;
  amount_rs: number; file_name: string | null; has_file: boolean;
  created_at: string; effective_rate_rs_kwh: number | null;
};

export type BillInput = {
  period: string; units_kwh: number; amount_rs: number;
  peak_demand_kw?: number | null; file_name?: string | null; file_base64?: string | null;
};

export const bills = {
  list: (facilityId: string) => request<Bill[]>(`/facilities/${facilityId}/bills`),
  upload: (facilityId: string, data: BillInput) =>
    request<Bill>(`/facilities/${facilityId}/bills`, { method: "POST", body: JSON.stringify(data) }),
  fileUrl: (facilityId: string, billId: string) => `${BASE}/facilities/${facilityId}/bills/${billId}/file`,
};

// ── Edge / Simulation ───────────────────────────────────────

export type EdgeSavings = {
  total_rs: number; solar_rs: number; arbitrage_rs: number;
  demand_rs: number; dg_rs: number;
  baseline_cost_rs: number; optimized_cost_rs: number;
  load_kwh: number; intervals: number; sim_hours: number;
};

export type EdgeLive = {
  telemetry: {
    site_id: string; soc_pct: number; solar_w: number; total_load_w: number;
    grid_charge_active: boolean; grid_charge_w: number; charge_source: string;
    tariff_period: string; tariff_rs_kwh: number; sim_hour: number;
    grid_on: boolean; battery_on: boolean; solar_on: boolean; dg_on: boolean;
    dg_w: number;
    circuits: { name: string; watts: number; active: boolean }[];
    received_at: string;
  } | null;
  commands: {
    grid_relay: boolean; solar_relay: boolean; battery_relay: boolean;
    dg_relay: boolean; grid_charge_relay: boolean; battery_discharge: boolean;
  };
  forecast: {
    available: boolean; samples: number; buckets: number;
    predicted_peak_kw: number; peak_hour: number; peak_in_hours: number | null;
    avg_next_3h_kw: number; solar_next_3h_kw: number;
    profile: Record<string, number>;
  } | null;
  savings: EdgeSavings | null;
};

export const edge = {
  live: (siteId = "sim-hospital-01") =>
    request<EdgeLive>(`/api/v1/edge/live?site_id=${siteId}`),
  resetSavings: (siteId = "sim-hospital-01") =>
    request<{ status: string }>(`/api/v1/edge/savings/reset?site_id=${siteId}`, { method: "POST" }),
};

// ── Alerts ───────────────────────────────────────────────────

export type Alert = {
  id: string; facility_id: string; severity: string; type: string;
  message: string; value: number | null; acknowledged_at: string | null; created_at: string;
};

export const alerts = {
  list: (facilityId: string, params?: { severity?: string; unacknowledged_only?: boolean }) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return request<Alert[]>(`/facilities/${facilityId}/alerts${q ? `?${q}` : ""}`);
  },
  acknowledge: (facilityId: string, alertId: string) =>
    request(`/facilities/${facilityId}/alerts/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ alert_id: alertId }),
    }),
  solarHealth: (facilityId: string) =>
    request<{ status: string; alerts: object[]; performance_ratio: number; checked_at?: string }>(
      `/facilities/${facilityId}/solar/health`
    ),
};

// ── Grid ─────────────────────────────────────────────────────

export type GridState = {
  facility_id: string; mode: string; main_breaker: boolean;
  battery_command: string; grid_voltage_v: number | null;
  grid_frequency_hz: number | null; last_mode_change: string;
};

export const grid = {
  state: (facilityId: string) =>
    request<GridState>(`/facilities/${facilityId}/grid/state`),
  loads: (facilityId: string) =>
    request<object[]>(`/facilities/${facilityId}/grid/loads`),
  island: (facilityId: string, reason: string) =>
    request<{ command_id: string; expires_at: string; message: string }>(
      `/facilities/${facilityId}/grid/island`,
      { method: "POST", body: JSON.stringify({ reason }) }
    ),
  confirm: (facilityId: string, commandId: string) =>
    request(`/facilities/${facilityId}/grid/confirm`, {
      method: "POST",
      body: JSON.stringify({ command_id: commandId }),
    }),
};
