-- ============================================================
-- MicroGrid AI — Performance Indexes
-- Migration 002
-- ============================================================

-- READINGS: primary query pattern is facility + time range
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_readings_facility_ts
    ON readings (facility_id, timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_readings_facility_ts_source
    ON readings (facility_id, timestamp DESC, source);

-- ALERTS: alert history + unacknowledged alerts
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_facility_created
    ON alerts (facility_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_unacknowledged
    ON alerts (facility_id, severity, created_at DESC)
    WHERE acknowledged_at IS NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_tenant
    ON alerts (tenant_id, created_at DESC);

-- AUDIT LOG: compliance queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_facility_created
    ON audit_log (facility_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_tenant_created
    ON audit_log (tenant_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_user
    ON audit_log (user_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_event
    ON audit_log (event, created_at DESC);

-- CONTROL COMMANDS: pending + unconfirmed commands
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_commands_facility_created
    ON control_commands (facility_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_commands_pending
    ON control_commands (facility_id, created_at DESC)
    WHERE confirmed = FALSE AND executed = FALSE;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_commands_expired
    ON control_commands (expires_at)
    WHERE confirmed = FALSE AND executed = FALSE;

-- FACILITIES: tenant lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_facilities_tenant
    ON facilities (tenant_id);

-- USERS: email lookup (auth)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email
    ON users (email);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_tenant
    ON users (tenant_id);

-- API KEYS: fast key lookup on ingest
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_api_keys_hash
    ON api_keys (key_hash);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_api_keys_facility
    ON api_keys (facility_id);

-- LOAD CONFIGS: facility load list
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_load_configs_facility
    ON load_configs (facility_id, priority, shed_order);

-- READINGS HOURLY: chart queries (last N days)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_readings_hourly_facility_hour
    ON readings_hourly (facility_id, hour DESC);

-- REPORTS: facility report history
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reports_facility
    ON reports (facility_id, created_at DESC);
