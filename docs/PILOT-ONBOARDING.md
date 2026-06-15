# Connecting a real meter/site to a facility

How device telemetry reaches the shadow-savings page. Do this once per pilot site.

## The data path (after the bridge)

```
ESP32 / meter ──POST /api/v1/ingest──▶ telemetry table        (edge page)
   (device key)                         │
                                        └─ bridge ─▶ readings table ─▶ /savings/shadow page
                                           (only if facilities.site_id matches)
```

The bridge mirrors each telemetry sample into the facility `readings` table — but
**only when a facility's `site_id` matches the device's `site_id`.** No mapping =
silent no-op (edge path unchanged).

## One-time steps for a pilot

1. **Apply the migration** (Supabase → SQL editor), once per database:
   ```sql
   -- backend/migrations/2026_06_add_facility_site_id.sql
   ALTER TABLE facilities ADD COLUMN IF NOT EXISTS site_id TEXT;
   CREATE UNIQUE INDEX IF NOT EXISTS idx_facilities_site_id
     ON facilities (site_id) WHERE site_id IS NOT NULL;
   ```

2. **Map the site to the facility.** Pick the facility UUID and the site_id the
   device will use, then:
   ```sql
   UPDATE facilities SET site_id = 'apollo-kolkata-01'
   WHERE id = '<facility-uuid>';
   ```

3. **Mint a device key** for that site (admin JWT):
   ```
   POST /api/v1/devices   {"site_id": "apollo-kolkata-01", "label": "meter-1"}
   ```
   Store the returned `dk_..._...` — shown once.

4. **Flash the firmware** with that `SITE_ID` and `DEVICE_KEY` (and the meter's
   Modbus read once wired). It posts to `/api/v1/ingest` as usual.

5. **Verify:** after data flows, `GET /facilities/{id}/savings/shadow?days=7`
   should move off `insufficient_data` once ~20+ hours of readings exist, and the
   dashboard Savings page shows measured ₹.

## Notes

- The bridge writes a `readings` row per telemetry post (`source='meter'`). The
  meter firmware posts ~once/minute, so ~1440 rows/day/site — fine. If you ever
  feed at multi-Hz, add a throttle (skip if last reading < 60 s old).
- `soc_pct`, `grid_kw`, `net_kw` are derived from the sample; for a meter-only
  shadow site (no battery) `soc_pct` will be 0 and that's expected.
- Rotate the demo device key (`dk_102bf365...`, committed in the repo) before any
  real pilot — mint a fresh one and keep it out of git.
