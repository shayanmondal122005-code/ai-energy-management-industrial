-- Bridge enabler: link an edge device's site_id to a facility, so device
-- telemetry (/api/v1/ingest) mirrors into the facility `readings` table that
-- powers shadow-savings and history. Run once in the Supabase SQL editor.
-- Safe to re-run (idempotent).

ALTER TABLE facilities ADD COLUMN IF NOT EXISTS site_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_facilities_site_id
  ON facilities (site_id) WHERE site_id IS NOT NULL;

-- Then map a site to a facility (one device's site_id -> one facility):
--   UPDATE facilities SET site_id = 'sim-hospital-01'
--   WHERE id = '<facility-uuid>';
--
-- Until a facility has site_id set, the bridge is a silent no-op and the edge
-- path behaves exactly as before.
