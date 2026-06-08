-- MicroGrid AI — full schema (Neon/Postgres)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS tenants (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name       TEXT NOT NULL,
  plan       VARCHAR(20) NOT NULL DEFAULT 'starter',
  is_active  BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS facilities (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  city         TEXT NOT NULL DEFAULT 'Kolkata',
  lat          DOUBLE PRECISION NOT NULL DEFAULT 22.57,
  lon          DOUBLE PRECISION NOT NULL DEFAULT 88.36,
  state_tariff TEXT NOT NULL DEFAULT 'West Bengal - CESC',
  battery_kwh  DOUBLE PRECISION NOT NULL DEFAULT 500,
  solar_kw     DOUBLE PRECISION NOT NULL DEFAULT 200,
  avg_load_kw  DOUBLE PRECISION NOT NULL DEFAULT 300,
  timezone     TEXT NOT NULL DEFAULT 'Asia/Kolkata',
  is_active    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT,
  role          VARCHAR(20) NOT NULL DEFAULT 'viewer',
  whatsapp      TEXT,
  full_name     TEXT,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  last_login_at TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_keys (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  facility_id  UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  key_hash     TEXT NOT NULL UNIQUE,
  label        TEXT NOT NULL,
  is_active    BOOLEAN NOT NULL DEFAULT TRUE,
  last_used_at TIMESTAMPTZ,
  created_by   UUID REFERENCES users(id),
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS readings (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  facility_id  UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  timestamp    TIMESTAMPTZ NOT NULL,
  load_kw      DOUBLE PRECISION NOT NULL,
  solar_kw     DOUBLE PRECISION NOT NULL DEFAULT 0,
  battery_soc  DOUBLE PRECISION NOT NULL DEFAULT 0,
  battery_temp DOUBLE PRECISION,
  grid_kw      DOUBLE PRECISION DEFAULT 0,
  net_kw       DOUBLE PRECISION DEFAULT 0,
  source       VARCHAR(20) NOT NULL DEFAULT 'unknown',
  created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_readings_facility_ts ON readings(facility_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS alerts (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  facility_id      UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  severity         VARCHAR(20) NOT NULL,
  type             TEXT NOT NULL,
  message          TEXT NOT NULL,
  value            DOUBLE PRECISION,
  threshold        DOUBLE PRECISION,
  whatsapp_sent    BOOLEAN NOT NULL DEFAULT FALSE,
  whatsapp_sent_at TIMESTAMPTZ,
  acknowledged_at  TIMESTAMPTZ,
  acknowledged_by  UUID REFERENCES users(id),
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS control_commands (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  facility_id   UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  type          VARCHAR(30) NOT NULL,
  target        TEXT,
  value         DOUBLE PRECISION,
  reason        TEXT NOT NULL,
  priority      VARCHAR(20) NOT NULL DEFAULT 'normal',
  confirmed     BOOLEAN NOT NULL DEFAULT FALSE,
  confirmed_at  TIMESTAMPTZ,
  confirmed_by  UUID REFERENCES users(id),
  executed      BOOLEAN NOT NULL DEFAULT FALSE,
  executed_at   TIMESTAMPTZ,
  result        VARCHAR(20),
  error_message TEXT,
  issued_by     UUID REFERENCES users(id),
  issued_by_ip  INET,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  expires_at    TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  facility_id UUID REFERENCES facilities(id) ON DELETE SET NULL,
  tenant_id   UUID REFERENCES tenants(id) ON DELETE SET NULL,
  user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
  event       TEXT NOT NULL,
  data        JSONB,
  ip_address  INET,
  user_agent  TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS grid_state (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  facility_id       UUID NOT NULL UNIQUE REFERENCES facilities(id) ON DELETE CASCADE,
  mode              VARCHAR(20) NOT NULL DEFAULT 'GRID_CONNECTED',
  main_breaker      BOOLEAN NOT NULL DEFAULT TRUE,
  battery_command   VARCHAR(20) NOT NULL DEFAULT 'HOLD',
  grid_voltage_v    DOUBLE PRECISION,
  grid_frequency_hz DOUBLE PRECISION,
  last_mode_change  TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS load_configs (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  facility_id  UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  load_id      TEXT NOT NULL,
  name         TEXT NOT NULL,
  priority     INTEGER NOT NULL,
  rated_kw     DOUBLE PRECISION NOT NULL,
  contactor_id TEXT,
  is_on        BOOLEAN NOT NULL DEFAULT TRUE,
  shed_order   INTEGER,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (facility_id, load_id)
);

CREATE TABLE IF NOT EXISTS reports (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  facility_id  UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  type         VARCHAR(20) NOT NULL DEFAULT 'weekly',
  period_start TIMESTAMPTZ NOT NULL,
  period_end   TIMESTAMPTZ NOT NULL,
  file_url     TEXT,
  status       VARCHAR(20) NOT NULL DEFAULT 'pending',
  generated_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Customer electricity bills — uploaded from the dashboard. Monthly aggregates
-- calibrate the savings/ROI engine and provide a verified baseline.
CREATE TABLE IF NOT EXISTS bills (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  facility_id    UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  period         TEXT,                 -- e.g. "May 2026"
  units_kwh      FLOAT,
  peak_demand_kw FLOAT,
  amount_rs      FLOAT,
  file_name      TEXT,
  file_data      BYTEA,                -- the uploaded bill (PDF/image), optional
  created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bills_facility ON bills(facility_id, created_at DESC);

-- Per-device API keys — each microcontroller gets its own site-scoped key.
-- Stolen device → revoke ONE key, only ITS site affected, never others.
CREATE TABLE IF NOT EXISTS device_keys (
  id           TEXT PRIMARY KEY,          -- public key id
  site_id      TEXT NOT NULL,
  key_hash     TEXT NOT NULL,             -- bcrypt of the secret (plaintext never stored)
  label        TEXT,
  is_active    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  last_used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_device_keys_site ON device_keys(site_id);

-- Wokwi ESP32 simulation telemetry (Prakriti Energy edge bridge)
CREATE TABLE IF NOT EXISTS telemetry (
  id SERIAL PRIMARY KEY,
  site_id TEXT NOT NULL,
  ts BIGINT,
  recorded_at TIMESTAMPTZ DEFAULT NOW(),
  soc_pct FLOAT,
  solar_w FLOAT,
  total_load_w FLOAT,
  sim_hour FLOAT,
  grid_charge_active BOOLEAN,
  grid_charge_w FLOAT,
  charge_source TEXT,
  tariff_period TEXT,
  tariff_rs_kwh FLOAT,
  grid_on BOOLEAN,
  battery_on BOOLEAN,
  solar_on BOOLEAN,
  dg_on BOOLEAN,
  circuits JSONB
);
CREATE INDEX IF NOT EXISTS idx_telemetry_site_ts ON telemetry(site_id, recorded_at DESC);

-- Hourly aggregation view used by the dashboard trend charts
CREATE OR REPLACE VIEW readings_hourly AS
SELECT facility_id,
       date_trunc('hour', timestamp) AS hour,
       AVG(load_kw)     AS load_kw_avg,
       AVG(solar_kw)    AS solar_kw_avg,
       AVG(battery_soc) AS battery_soc_avg
FROM readings
GROUP BY facility_id, date_trunc('hour', timestamp);
