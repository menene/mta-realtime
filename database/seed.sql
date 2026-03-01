-- seed.sql
-- Populates lookup tables with initial data.
-- Safe to re-run: only inserts when the table is empty.

-- ─────────────────────────────────────────────
--  Routes (MTA subway lines)
-- ─────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM routes LIMIT 1) THEN
        INSERT INTO routes (name) VALUES
            ('1'), ('2'), ('3'), ('4'), ('5'), ('6'), ('7'),
            ('A'), ('B'), ('C'), ('D'), ('E'), ('F'), ('G'),
            ('J'), ('L'), ('M'), ('N'), ('Q'), ('R'), ('S'), ('W'), ('Z'),
            ('SF'),   -- Franklin Ave Shuttle
            ('SR'),   -- Rockaway Park Shuttle
            ('SIR');  -- Staten Island Railway
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
