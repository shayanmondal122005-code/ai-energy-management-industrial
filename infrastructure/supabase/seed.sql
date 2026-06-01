-- ============================================================
-- MicroGrid AI — Demo Seed Data
-- Apollo Hospital Kolkata — reference facility
-- ============================================================

-- Demo tenant
INSERT INTO tenants (id, name, plan) VALUES
    ('00000000-0000-0000-0000-000000000001', 'Apollo Hospitals Group', 'professional');

-- Demo facility: Apollo Multispeciality Hospital, Kolkata
INSERT INTO facilities (id, tenant_id, name, city, lat, lon, state_tariff,
                        battery_kwh, solar_kw, avg_load_kw)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    '00000000-0000-0000-0000-000000000001',
    'Apollo Multispeciality Hospital',
    'Kolkata', 22.5697, 88.3697,
    'West Bengal - CESC',
    500, 200, 300
);

-- Demo admin user (password set via Supabase Auth — this is just the profile)
INSERT INTO users (id, tenant_id, email, role, full_name) VALUES
    ('00000000-0000-0000-0000-000000000100',
     '00000000-0000-0000-0000-000000000001',
     'demo@apollohospital.in', 'tenant_admin', 'Demo Admin');

-- Grid state for demo facility
INSERT INTO grid_state (facility_id, mode, main_breaker, battery_command)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    'GRID_CONNECTED', TRUE, 'HOLD'
);

-- Load configs: Apollo Hospital priority ladder (24 loads, 580 kW total)
INSERT INTO load_configs (facility_id, load_id, name, priority, rated_kw, contactor_id, shed_order) VALUES
    -- P1: Life safety — NEVER shed
    ('00000000-0000-0000-0000-000000000010', 'ICU_POWER',       'ICU + Critical Care',         1, 45,  'CB-01', 1),
    ('00000000-0000-0000-0000-000000000010', 'OT_POWER',        'Operating Theatres',          1, 60,  'CB-02', 2),
    ('00000000-0000-0000-0000-000000000010', 'LIFE_SUPPORT',    'Life Support Equipment',      1, 20,  'CB-03', 3),
    ('00000000-0000-0000-0000-000000000010', 'EMERGENCY_LIGHT', 'Emergency Lighting',          1, 8,   'CB-04', 4),
    ('00000000-0000-0000-0000-000000000010', 'FIRE_ALARM',      'Fire Alarm + Suppression',    1, 5,   'CB-05', 5),
    -- P2: Essential medical
    ('00000000-0000-0000-0000-000000000010', 'RADIOLOGY',       'Radiology + MRI',             2, 80,  'CB-06', 1),
    ('00000000-0000-0000-0000-000000000010', 'PHARMACY',        'Pharmacy + Cold Chain',       2, 15,  'CB-07', 2),
    ('00000000-0000-0000-0000-000000000010', 'LAB',             'Pathology Laboratory',        2, 20,  'CB-08', 3),
    ('00000000-0000-0000-0000-000000000010', 'NICU',            'NICU Ward',                   2, 25,  'CB-09', 4),
    -- P3: Operational
    ('00000000-0000-0000-0000-000000000010', 'LIFTS',           'Elevators (Patient)',         3, 30,  'CB-10', 1),
    ('00000000-0000-0000-0000-000000000010', 'SERVER_ROOM',     'IT Server Room',              3, 20,  'CB-11', 2),
    ('00000000-0000-0000-0000-000000000010', 'KITCHEN',         'Hospital Kitchen',            3, 35,  'CB-12', 3),
    ('00000000-0000-0000-0000-000000000010', 'STERILISATION',   'CSSD Sterilisation',          3, 25,  'CB-13', 4),
    ('00000000-0000-0000-0000-000000000010', 'GENERAL_WARD_1',  'General Ward Block A',        3, 40,  'CB-14', 5),
    ('00000000-0000-0000-0000-000000000010', 'GENERAL_WARD_2',  'General Ward Block B',        3, 40,  'CB-15', 6),
    -- P4: Comfort
    ('00000000-0000-0000-0000-000000000010', 'AC_BLOCK_A',      'HVAC Block A',                4, 45,  'CB-16', 1),
    ('00000000-0000-0000-0000-000000000010', 'AC_BLOCK_B',      'HVAC Block B',                4, 45,  'CB-17', 2),
    ('00000000-0000-0000-0000-000000000010', 'ADMIN_WING',      'Administrative Wing',         4, 20,  'CB-18', 3),
    ('00000000-0000-0000-0000-000000000010', 'CANTEEN',         'Staff Canteen',               4, 15,  'CB-19', 4),
    ('00000000-0000-0000-0000-000000000010', 'GENERAL_LIGHT',   'General Corridor Lighting',   4, 12,  'CB-20', 5),
    -- P5: Non-essential (shed first)
    ('00000000-0000-0000-0000-000000000010', 'PARKING',         'Parking Lot Lighting',        5, 8,   'CB-21', 1),
    ('00000000-0000-0000-0000-000000000010', 'EV_CHARGING',     'EV Charging Station',         5, 22,  'CB-22', 2),
    ('00000000-0000-0000-0000-000000000010', 'WATER_HEATER',    'Non-critical Water Heating',  5, 10,  'CB-23', 3),
    ('00000000-0000-0000-0000-000000000010', 'SIGNAGE',         'External Signage',            5, 5,   'CB-24', 4);
