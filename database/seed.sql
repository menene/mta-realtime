-- seed.sql
-- Populates lookup tables with initial data.
-- Safe to re-run: only inserts when the table is empty.

-- ─────────────────────────────────────────────
--  Routes (MTA subway lines)
-- ─────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM routes LIMIT 1) THEN
        INSERT INTO routes (name, long_name, route_type, route_color, text_color, sort_order) VALUES
            ('A',  '8 Avenue Express',              1, '0062CF', 'FFFFFF',  1),
            ('C',  '8 Avenue Local',                1, '0062CF', 'FFFFFF',  2),
            ('E',  '8 Avenue Local',                1, '0062CF', 'FFFFFF',  3),
            ('B',  '6 Avenue Express',              1, 'EB6800', 'FFFFFF',  4),
            ('D',  '6 Avenue Express',              1, 'EB6800', 'FFFFFF',  5),
            ('F',  'Queens Blvd Express/6 Av Local',1, 'EB6800', 'FFFFFF',  6),
            ('FX', 'Brooklyn F Express',            1, 'EB6800', 'FFFFFF',  7),
            ('M',  'Queens Blvd Local/6 Av Local',  1, 'EB6800', 'FFFFFF',  8),
            ('G',  'Brooklyn-Queens Crosstown',     1, '799534', 'FFFFFF',  9),
            ('J',  'Nassau St Local',               1, '8E5C33', 'FFFFFF', 10),
            ('Z',  'Nassau St Express',             1, '8E5C33', 'FFFFFF', 11),
            ('L',  '14 St-Canarsie Local',          1, '7C858C', 'FFFFFF', 12),
            ('N',  'Broadway Local',                1, 'F6BC26', '000000', 13),
            ('Q',  'Broadway Express',              1, 'F6BC26', '000000', 14),
            ('R',  'Broadway Local',                1, 'F6BC26', '000000', 15),
            ('W',  'Broadway Local',                1, 'F6BC26', '000000', 16),
            ('GS', '42 St Shuttle',                 1, '7C858C', 'FFFFFF', 17),
            ('FS', 'Franklin Avenue Shuttle',       1, '7C858C', 'FFFFFF', 18),
            ('H',  'Rockaway Park Shuttle',         1, '7C858C', 'FFFFFF', 19),
            ('1',  'Broadway - 7 Avenue Local',     1, 'D82233', 'FFFFFF', 20),
            ('2',  '7 Avenue Express',              1, 'D82233', 'FFFFFF', 21),
            ('3',  '7 Avenue Express',              1, 'D82233', 'FFFFFF', 22),
            ('4',  'Lexington Avenue Express',      1, '009952', 'FFFFFF', 23),
            ('5',  'Lexington Avenue Express',      1, '009952', 'FFFFFF', 24),
            ('6',  'Lexington Avenue Local',        1, '009952', 'FFFFFF', 25),
            ('6X', 'Pelham Bay Park Express',       1, '009952', 'FFFFFF', 26),
            ('7',  'Flushing Local',                1, '9A38A1', 'FFFFFF', 27),
            ('7X', 'Flushing Express',              1, '9A38A1', 'FFFFFF', 28),
            ('SI', 'Staten Island Railway',         2, '08179C', 'FFFFFF', 29);
    END IF;
END $$;

-- ─────────────────────────────────────────────
--  Train Statuses (GTFS-realtime vehicle statuses)
-- ─────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM train_statuses LIMIT 1) THEN
        INSERT INTO train_statuses (name) VALUES
            ('STOPPED_AT'),
            ('IN_TRANSIT_TO'),
            ('INCOMING_AT');
    END IF;
END $$;

-- ─────────────────────────────────────────────
--  Calendar (GTFS service patterns)
-- ─────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM calendar LIMIT 1) THEN
        INSERT INTO calendar (service_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date) VALUES
            ('Weekday',  1, 1, 1, 1, 1, 0, 0, '20260301', '20260516'),
            ('Saturday', 0, 0, 0, 0, 0, 1, 0, '20260301', '20260516'),
            ('Sunday',   0, 0, 0, 0, 0, 0, 1, '20260301', '20260516');
    END IF;
END $$;
