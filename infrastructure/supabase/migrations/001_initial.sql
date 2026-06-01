-- ============================================================
-- MicroGrid AI — Initial Schema
-- Migration 001: All tables, foreign keys, RLS policies
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_cron";

-- ============================================================
-- TENANTS
-- ============================================================
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    plan        TEXT NOT NULL DEFAULT 'starter' CHECK (plan IN ('starter','professional','enterprise')),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- FACILITIES
-- ============================================================
CREATE TABLE facilities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    city            TEXT NOT NULL DEFAULT 'Kolkata',
    lat             DOUBLE PRECISION NOT NULL DEFAULT 22.57,
    lon             DOUBLE PRECISION NOT NULL DEFAULT 88.36,
    state_tariff    TEXT NOT NULL DEFAULT 'West Bengal - CESC',
    battery_kwh     DOUBLE PRECISION NOT NULL DEFAULT 500,
    solar_kw        DOUBLE PRECISION NOT NULL DEFAULT 200,
    avg_load_kw     DOUBLE PRECISION NOT NULL DEFAULT 300,
    timezone        TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- USERS
-- ============================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           TEXT NOT NULL UNIQUE,
    role            TEXT NOT NULL DEFAULT 'viewer'
                        CHECK (role IN ('super_admin','tenant_admin','operator','viewer','api_key')),
    whatsapp        TEXT,           -- encrypted at application layer
    full_name       TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- API KEYS  (IoT gateways — scoped to one facility)
-- ============================================================
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    facility_id     UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    key_hash        TEXT NOT NULL UNIQUE,   -- bcrypt hash of the actual key
    label           TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at    TIMESTAMPTZ,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- READINGS  (partitioned by month for timeseries performance)
-- ============================================================
CREATE TABLE readings (
    id              UUID DEFAULT uuid_generate_v4(),
    facility_id     UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    timestamp       TIMESTAMPTZ NOT NULL,
    load_kw         DOUBLE PRECISION NOT NULL,
    solar_kw        DOUBLE PRECISION NOT NULL DEFAULT 0,
    battery_soc     DOUBLE PRECISION NOT NULL DEFAULT 0,
    battery_temp    DOUBLE PRECISION,
    grid_kw         DOUBLE PRECISION DEFAULT 0,
    net_kw          DOUBLE PRECISION DEFAULT 0,
    source          TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (source IN ('iot_gateway','feeder','simulated','manual')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Create monthly partitions for current year + next year
DO $$
DECLARE
    start_date DATE := DATE_TRUNC('year', NOW())::DATE;
    end_date   DATE := (DATE_TRUNC('year', NOW()) + INTERVAL '2 years')::DATE;
    cur_date   DATE := start_date;
    part_name  TEXT;
    next_date  DATE;
BEGIN
    WHILE cur_date < end_date LOOP
        next_date := cur_date + INTERVAL '1 month';
        part_name := 'readings_' || TO_CHAR(cur_date, 'YYYY_MM');
        EXECUTE FORMAT(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF readings
             FOR VALUES FROM (%L) TO (%L)',
            part_name, cur_date, next_date
        );
        cur_date := next_date;
    END LOOP;
END $$;

-- ============================================================
-- ALERTS
-- ============================================================
CREATE TABLE alerts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id         UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    severity            TEXT NOT NULL CHECK (severity IN ('critical','warning','info','ok')),
    type                TEXT NOT NULL,  -- e.g. 'BATTERY_CRITICAL', 'SOILING', 'DEMAND_PEAK'
    message             TEXT NOT NULL,
    value               DOUBLE PRECISION,   -- the metric value that triggered the alert
    threshold           DOUBLE PRECISION,   -- the threshold that was crossed
    whatsapp_sent       BOOLEAN NOT NULL DEFAULT FALSE,
    whatsapp_sent_at    TIMESTAMPTZ,
    acknowledged_at     TIMESTAMPTZ,
    acknowledged_by     UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- CONTROL COMMANDS  (grid switching, load shed/restore)
-- ============================================================
CREATE TABLE control_commands (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id     UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    type            TEXT NOT NULL CHECK (type IN (
                        'ISLAND','RECONNECT','LOAD_SHED','LOAD_RESTORE',
                        'EMERGENCY_STOP','BATTERY_CHARGE','BATTERY_DISCHARGE'
                    )),
    target          TEXT,           -- load_id or 'grid' or 'battery'
    value           DOUBLE PRECISION,
    reason          TEXT NOT NULL,
    priority        TEXT NOT NULL DEFAULT 'normal'
                        CHECK (priority IN ('low','normal','high','emergency')),
    -- Two-step confirmation
    confirmed       BOOLEAN NOT NULL DEFAULT FALSE,
    confirmed_at    TIMESTAMPTZ,
    confirmed_by    UUID REFERENCES users(id),
    -- Execution
    executed        BOOLEAN NOT NULL DEFAULT FALSE,
    executed_at     TIMESTAMPTZ,
    result          TEXT,           -- 'success' | 'failed' | 'timeout'
    error_message   TEXT,
    -- Issued by
    issued_by       UUID REFERENCES users(id),
    issued_by_ip    INET,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Safety: commands expire after 60 seconds if not confirmed
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '60 seconds')
);

-- ============================================================
-- AUDIT LOG  (append-only — no user can delete rows)
-- ============================================================
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id     UUID REFERENCES facilities(id) ON DELETE SET NULL,
    tenant_id       UUID REFERENCES tenants(id) ON DELETE SET NULL,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    event           TEXT NOT NULL,  -- e.g. 'LOGIN', 'GRID_ISLAND', 'LOAD_SHED'
    data            JSONB,          -- full context snapshot
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- GRID STATE  (current mode per facility)
-- ============================================================
CREATE TABLE grid_state (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id         UUID NOT NULL UNIQUE REFERENCES facilities(id) ON DELETE CASCADE,
    mode                TEXT NOT NULL DEFAULT 'GRID_CONNECTED'
                            CHECK (mode IN (
                                'GRID_CONNECTED','ISLAND','TRANSITION',
                                'EMERGENCY','MAINTENANCE'
                            )),
    main_breaker        BOOLEAN NOT NULL DEFAULT TRUE,
    battery_command     TEXT NOT NULL DEFAULT 'HOLD'
                            CHECK (battery_command IN ('CHARGE','DISCHARGE','HOLD')),
    grid_voltage_v      DOUBLE PRECISION,
    grid_frequency_hz   DOUBLE PRECISION,
    last_mode_change    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- LOAD CONFIGS  (facility loads with priority ladder)
-- ============================================================
CREATE TABLE load_configs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id     UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    load_id         TEXT NOT NULL,      -- e.g. 'ICU_POWER', 'AC_BLOCK_A'
    name            TEXT NOT NULL,
    priority        INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
    rated_kw        DOUBLE PRECISION NOT NULL,
    contactor_id    TEXT,               -- physical relay/contactor ID
    is_on           BOOLEAN NOT NULL DEFAULT TRUE,
    shed_order      INTEGER,            -- order in which to shed at same priority
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (facility_id, load_id)
);

-- ============================================================
-- REPORTS  (generated PDF reports)
-- ============================================================
CREATE TABLE reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id     UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    type            TEXT NOT NULL DEFAULT 'weekly'
                        CHECK (type IN ('weekly','monthly','incident','custom')),
    period_start    TIMESTAMPTZ NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    file_url        TEXT,           -- Supabase Storage signed URL
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','generating','ready','failed')),
    generated_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- HOURLY AGGREGATES  (pre-computed for fast chart queries)
-- ============================================================
CREATE TABLE readings_hourly (
    facility_id     UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    hour            TIMESTAMPTZ NOT NULL,
    load_kw_avg     DOUBLE PRECISION,
    load_kw_max     DOUBLE PRECISION,
    solar_kw_avg    DOUBLE PRECISION,
    solar_kw_max    DOUBLE PRECISION,
    battery_soc_avg DOUBLE PRECISION,
    battery_soc_min DOUBLE PRECISION,
    grid_kw_avg     DOUBLE PRECISION,
    reading_count   INTEGER,
    PRIMARY KEY (facility_id, hour)
);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

ALTER TABLE tenants          ENABLE ROW LEVEL SECURITY;
ALTER TABLE facilities       ENABLE ROW LEVEL SECURITY;
ALTER TABLE users            ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys         ENABLE ROW LEVEL SECURITY;
ALTER TABLE readings         ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts           ENABLE ROW LEVEL SECURITY;
ALTER TABLE control_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log        ENABLE ROW LEVEL SECURITY;
ALTER TABLE grid_state       ENABLE ROW LEVEL SECURITY;
ALTER TABLE load_configs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports          ENABLE ROW LEVEL SECURITY;
ALTER TABLE readings_hourly  ENABLE ROW LEVEL SECURITY;

-- Helper: extract tenant_id from JWT claims
CREATE OR REPLACE FUNCTION auth_tenant_id() RETURNS UUID AS $$
    SELECT NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID;
$$ LANGUAGE SQL STABLE;

CREATE OR REPLACE FUNCTION auth_role() RETURNS TEXT AS $$
    SELECT NULLIF(current_setting('app.role', TRUE), '');
$$ LANGUAGE SQL STABLE;

CREATE OR REPLACE FUNCTION is_super_admin() RETURNS BOOLEAN AS $$
    SELECT auth_role() = 'super_admin';
$$ LANGUAGE SQL STABLE;

-- TENANTS: super_admin sees all; others see only their own
CREATE POLICY tenants_select ON tenants FOR SELECT
    USING (is_super_admin() OR id = auth_tenant_id());

CREATE POLICY tenants_insert ON tenants FOR INSERT
    WITH CHECK (is_super_admin());

CREATE POLICY tenants_update ON tenants FOR UPDATE
    USING (is_super_admin());

-- FACILITIES: users see only their tenant's facilities
CREATE POLICY facilities_select ON facilities FOR SELECT
    USING (is_super_admin() OR tenant_id = auth_tenant_id());

CREATE POLICY facilities_insert ON facilities FOR INSERT
    WITH CHECK (is_super_admin() OR (tenant_id = auth_tenant_id() AND auth_role() IN ('tenant_admin','super_admin')));

CREATE POLICY facilities_update ON facilities FOR UPDATE
    USING (is_super_admin() OR (tenant_id = auth_tenant_id() AND auth_role() IN ('tenant_admin','super_admin')));

-- USERS: users see only their tenant
CREATE POLICY users_select ON users FOR SELECT
    USING (is_super_admin() OR tenant_id = auth_tenant_id());

CREATE POLICY users_insert ON users FOR INSERT
    WITH CHECK (is_super_admin() OR (tenant_id = auth_tenant_id() AND auth_role() IN ('tenant_admin','super_admin')));

CREATE POLICY users_update ON users FOR UPDATE
    USING (is_super_admin() OR (tenant_id = auth_tenant_id() AND auth_role() IN ('tenant_admin','super_admin')));

-- READINGS: tenant-scoped; api_key can insert for its facility
CREATE POLICY readings_select ON readings FOR SELECT
    USING (is_super_admin() OR facility_id IN (
        SELECT id FROM facilities WHERE tenant_id = auth_tenant_id()
    ));

CREATE POLICY readings_insert ON readings FOR INSERT
    WITH CHECK (facility_id IN (
        SELECT id FROM facilities WHERE tenant_id = auth_tenant_id()
    ));

-- ALERTS: tenant-scoped
CREATE POLICY alerts_select ON alerts FOR SELECT
    USING (is_super_admin() OR tenant_id = auth_tenant_id());

CREATE POLICY alerts_insert ON alerts FOR INSERT
    WITH CHECK (is_super_admin() OR tenant_id = auth_tenant_id());

CREATE POLICY alerts_update ON alerts FOR UPDATE
    USING (is_super_admin() OR (tenant_id = auth_tenant_id() AND auth_role() IN ('operator','tenant_admin','super_admin')));

-- CONTROL COMMANDS: operator+ can insert; all can read
CREATE POLICY commands_select ON control_commands FOR SELECT
    USING (is_super_admin() OR tenant_id = auth_tenant_id());

CREATE POLICY commands_insert ON control_commands FOR INSERT
    WITH CHECK (is_super_admin() OR (
        tenant_id = auth_tenant_id()
        AND auth_role() IN ('operator','tenant_admin','super_admin')
    ));

CREATE POLICY commands_update ON control_commands FOR UPDATE
    USING (is_super_admin() OR (
        tenant_id = auth_tenant_id()
        AND auth_role() IN ('operator','tenant_admin','super_admin')
    ));

-- AUDIT LOG: append-only — SELECT allowed, no UPDATE/DELETE for any user
CREATE POLICY audit_select ON audit_log FOR SELECT
    USING (is_super_admin() OR tenant_id = auth_tenant_id());

CREATE POLICY audit_insert ON audit_log FOR INSERT
    WITH CHECK (TRUE);  -- backend service role inserts only

-- GRID STATE: all tenant users read; operator+ write
CREATE POLICY grid_select ON grid_state FOR SELECT
    USING (is_super_admin() OR facility_id IN (
        SELECT id FROM facilities WHERE tenant_id = auth_tenant_id()
    ));

CREATE POLICY grid_update ON grid_state FOR UPDATE
    USING (is_super_admin() OR (
        facility_id IN (SELECT id FROM facilities WHERE tenant_id = auth_tenant_id())
        AND auth_role() IN ('operator','tenant_admin','super_admin')
    ));

-- LOAD CONFIGS
CREATE POLICY load_configs_select ON load_configs FOR SELECT
    USING (is_super_admin() OR facility_id IN (
        SELECT id FROM facilities WHERE tenant_id = auth_tenant_id()
    ));

CREATE POLICY load_configs_write ON load_configs FOR ALL
    USING (is_super_admin() OR (
        facility_id IN (SELECT id FROM facilities WHERE tenant_id = auth_tenant_id())
        AND auth_role() IN ('operator','tenant_admin','super_admin')
    ));

-- REPORTS
CREATE POLICY reports_select ON reports FOR SELECT
    USING (is_super_admin() OR tenant_id = auth_tenant_id());

-- READINGS HOURLY
CREATE POLICY readings_hourly_select ON readings_hourly FOR SELECT
    USING (is_super_admin() OR facility_id IN (
        SELECT id FROM facilities WHERE tenant_id = auth_tenant_id()
    ));

-- ============================================================
-- UPDATED_AT TRIGGERS
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tenants_updated_at    BEFORE UPDATE ON tenants    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER facilities_updated_at BEFORE UPDATE ON facilities FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER users_updated_at      BEFORE UPDATE ON users      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER load_configs_updated_at BEFORE UPDATE ON load_configs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER grid_state_updated_at BEFORE UPDATE ON grid_state FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- HOURLY AGGREGATION FUNCTION  (called by pg_cron every hour)
-- ============================================================
CREATE OR REPLACE FUNCTION aggregate_readings_hourly(p_facility_id UUID, p_hour TIMESTAMPTZ)
RETURNS VOID AS $$
BEGIN
    INSERT INTO readings_hourly (
        facility_id, hour,
        load_kw_avg, load_kw_max,
        solar_kw_avg, solar_kw_max,
        battery_soc_avg, battery_soc_min,
        grid_kw_avg, reading_count
    )
    SELECT
        facility_id,
        DATE_TRUNC('hour', timestamp) AS hour,
        AVG(load_kw), MAX(load_kw),
        AVG(solar_kw), MAX(solar_kw),
        AVG(battery_soc), MIN(battery_soc),
        AVG(grid_kw),
        COUNT(*)
    FROM readings
    WHERE facility_id = p_facility_id
      AND DATE_TRUNC('hour', timestamp) = DATE_TRUNC('hour', p_hour)
    GROUP BY facility_id, DATE_TRUNC('hour', timestamp)
    ON CONFLICT (facility_id, hour) DO UPDATE SET
        load_kw_avg     = EXCLUDED.load_kw_avg,
        load_kw_max     = EXCLUDED.load_kw_max,
        solar_kw_avg    = EXCLUDED.solar_kw_avg,
        solar_kw_max    = EXCLUDED.solar_kw_max,
        battery_soc_avg = EXCLUDED.battery_soc_avg,
        battery_soc_min = EXCLUDED.battery_soc_min,
        grid_kw_avg     = EXCLUDED.grid_kw_avg,
        reading_count   = EXCLUDED.reading_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- DATA RETENTION FUNCTION  (called by pg_cron daily midnight)
-- Keep raw 15-min readings for 90 days; hourly aggregates forever
-- ============================================================
CREATE OR REPLACE FUNCTION run_retention_policy()
RETURNS VOID AS $$
BEGIN
    DELETE FROM readings
    WHERE timestamp < NOW() - INTERVAL '90 days';

    RAISE NOTICE 'Retention policy ran at %', NOW();
END;
$$ LANGUAGE plpgsql;

-- Schedule with pg_cron (run after enabling in Supabase dashboard)
-- SELECT cron.schedule('hourly-aggregate', '5 * * * *', 'SELECT aggregate_readings_hourly(...)');
-- SELECT cron.schedule('daily-retention', '0 0 * * *', 'SELECT run_retention_policy()');
