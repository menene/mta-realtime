-- mta.sql
-- MTA Subway tables: lookup/dimension + realtime + static GTFS schedule.
-- Uses IF NOT EXISTS so it is safe to re-run — existing data is never touched.
-- Executed automatically on first postgres container start via docker-entrypoint-initdb.d.


-- ═══════════════════════════════════════════════════════════════════════════════
--  Lookup / Dimension Tables
-- ═══════════════════════════════════════════════════════════════════════════════

-- Routes (subway lines: G, F, A, 1, 7, etc.)
CREATE TABLE IF NOT EXISTS routes (
    id          SERIAL       PRIMARY KEY,
    name        VARCHAR(16)  NOT NULL UNIQUE,      -- GTFS route_id: "G", "F", "A", "1"
    long_name   VARCHAR(128),                      -- e.g. "8 Avenue Express"
    description TEXT,                              -- route_desc from GTFS
    route_type  SMALLINT,                          -- 1 = subway, 2 = rail
    route_url   VARCHAR(256),
    route_color VARCHAR(6),                        -- hex without #
    text_color  VARCHAR(6),
    sort_order  INTEGER
);

-- Train statuses
CREATE TABLE IF NOT EXISTS train_statuses (
    id      SERIAL      PRIMARY KEY,
    name    VARCHAR(20) NOT NULL UNIQUE      -- STOPPED_AT | IN_TRANSIT_TO | INCOMING_AT
);

-- Stops (station + direction: F27S, G34N, etc.)
CREATE TABLE IF NOT EXISTS stops (
    id              SERIAL        PRIMARY KEY,
    name            VARCHAR(16)   NOT NULL UNIQUE,  -- GTFS stop_id: "F27S", "G34N"
    stop_name       VARCHAR(64),                    -- human-readable name
    stop_lat        NUMERIC(9,6),
    stop_lon        NUMERIC(9,6),
    location_type   SMALLINT,                       -- 0 = stop, 1 = station
    parent_station  VARCHAR(16)
);

-- Trips (unique trip identifiers from the feed: 066900_G..S09X002, etc.)
CREATE TABLE IF NOT EXISTS trips (
    id      SERIAL       PRIMARY KEY,
    name    VARCHAR(64)  NOT NULL UNIQUE     -- e.g. "066900_G..S09X002"
);


-- ═══════════════════════════════════════════════════════════════════════════════
--  Static GTFS Schedule Tables
-- ═══════════════════════════════════════════════════════════════════════════════

-- Calendar (service patterns: Weekday, Saturday, Sunday)
CREATE TABLE IF NOT EXISTS calendar (
    service_id  VARCHAR(32) PRIMARY KEY,
    monday      SMALLINT NOT NULL,
    tuesday     SMALLINT NOT NULL,
    wednesday   SMALLINT NOT NULL,
    thursday    SMALLINT NOT NULL,
    friday      SMALLINT NOT NULL,
    saturday    SMALLINT NOT NULL,
    sunday      SMALLINT NOT NULL,
    start_date  VARCHAR(8) NOT NULL,
    end_date    VARCHAR(8) NOT NULL
);

-- Calendar date exceptions
CREATE TABLE IF NOT EXISTS calendar_dates (
    service_id     VARCHAR(32) NOT NULL REFERENCES calendar(service_id),
    date           VARCHAR(8)  NOT NULL,
    exception_type SMALLINT    NOT NULL,
    PRIMARY KEY (service_id, date)
);

-- Scheduled trips (from GTFS static feed)
CREATE TABLE IF NOT EXISTS scheduled_trips (
    trip_id        VARCHAR(128) PRIMARY KEY,
    route_id       VARCHAR(8)   NOT NULL,
    service_id     VARCHAR(32)  NOT NULL REFERENCES calendar(service_id),
    trip_headsign  VARCHAR(64),
    direction_id   SMALLINT,
    shape_id       VARCHAR(32)
);

CREATE INDEX IF NOT EXISTS idx_st_route   ON scheduled_trips (route_id);
CREATE INDEX IF NOT EXISTS idx_st_service ON scheduled_trips (service_id);

-- Scheduled stop times
CREATE TABLE IF NOT EXISTS stop_times (
    trip_id        VARCHAR(128) NOT NULL REFERENCES scheduled_trips(trip_id),
    stop_id        VARCHAR(16)  NOT NULL,
    arrival_time   VARCHAR(8)   NOT NULL,    -- HH:MM:SS (can exceed 24:00:00)
    departure_time VARCHAR(8)   NOT NULL,
    stop_sequence  INTEGER      NOT NULL,
    PRIMARY KEY (trip_id, stop_sequence)
);

CREATE INDEX IF NOT EXISTS idx_stime_stop    ON stop_times (stop_id);
CREATE INDEX IF NOT EXISTS idx_stime_arrival ON stop_times (arrival_time);


-- ═══════════════════════════════════════════════════════════════════════════════
--  1. Vehicle Positions
--     Snapshot of where each train is at a given moment.
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS vehicle_positions (
    id              BIGSERIAL       PRIMARY KEY,

    -- foreign keys (populated by the web service)
    route_id        INTEGER         REFERENCES routes(id),
    trip_id         INTEGER         REFERENCES trips(id),
    stop_id         INTEGER         REFERENCES stops(id),
    status_id       INTEGER         REFERENCES train_statuses(id),

    -- position info
    current_stop_sequence   INTEGER,
    start_time              VARCHAR(8),     -- HH:MM:SS
    start_date              VARCHAR(8),     -- YYYYMMDD
    direction_id            SMALLINT,       -- 0 = northbound, 1 = southbound

    -- feed timestamp (unix epoch from the MTA feed)
    timestamp       BIGINT          NOT NULL,

    -- when the row was inserted
    recorded_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Prevent exact duplicate rows
CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicle_pos
    ON vehicle_positions (trip_id, timestamp);

-- Common query patterns
CREATE INDEX IF NOT EXISTS idx_vp_route      ON vehicle_positions (route_id);
CREATE INDEX IF NOT EXISTS idx_vp_stop       ON vehicle_positions (stop_id);
CREATE INDEX IF NOT EXISTS idx_vp_timestamp  ON vehicle_positions (timestamp);
CREATE INDEX IF NOT EXISTS idx_vp_recorded   ON vehicle_positions (recorded_at);


-- ═══════════════════════════════════════════════════════════════════════════════
--  2. Time Updates (Trip Updates)
--     Predicted arrival / departure times for upcoming stops.
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS time_updates (
    id              BIGSERIAL       PRIMARY KEY,

    -- foreign keys (populated by the web service)
    route_id        INTEGER         REFERENCES routes(id),
    trip_id         INTEGER         REFERENCES trips(id),
    stop_id         INTEGER         REFERENCES stops(id),

    -- trip context
    start_time      VARCHAR(8),         -- HH:MM:SS
    start_date      VARCHAR(8),         -- YYYYMMDD
    direction_id    SMALLINT,           -- 0 = northbound, 1 = southbound

    -- stop predictions (unix epoch)
    arrival_time    BIGINT,             -- when the train reaches the stop
    departure_time  BIGINT,             -- when the train leaves the stop

    -- when the row was inserted
    recorded_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Prevent exact duplicate predictions
CREATE UNIQUE INDEX IF NOT EXISTS uq_time_update
    ON time_updates (trip_id, stop_id, start_date, arrival_time);

-- Common query patterns
CREATE INDEX IF NOT EXISTS idx_tu_route     ON time_updates (route_id);
CREATE INDEX IF NOT EXISTS idx_tu_stop      ON time_updates (stop_id);
CREATE INDEX IF NOT EXISTS idx_tu_arrival   ON time_updates (arrival_time);
CREATE INDEX IF NOT EXISTS idx_tu_recorded  ON time_updates (recorded_at);


-- ═══════════════════════════════════════════════════════════════════════════════
--  Gold-Tier Views — Enriched data for visualization & delay detection
-- ═══════════════════════════════════════════════════════════════════════════════

-- v_gold_vehicle_positions: enriched snapshot of where trains are
CREATE OR REPLACE VIEW v_gold_vehicle_positions AS
SELECT
    vp.id,
    vp.recorded_at,
    TO_TIMESTAMP(vp.timestamp)          AS timestamp,
    r.name                              AS route,
    r.route_color,
    r.text_color,
    t.name                              AS trip_name,
    s.name                              AS stop_code,
    s.stop_name,
    s.stop_lat,
    s.stop_lon,
    ts.name                             AS train_status,
    CASE vp.direction_id
        WHEN 0 THEN 'N'
        WHEN 1 THEN 'S'
    END                                 AS direction,
    vp.current_stop_sequence,
    vp.start_time,
    vp.start_date
FROM vehicle_positions vp
INNER JOIN routes         r  ON r.id  = vp.route_id
INNER JOIN trips          t  ON t.id  = vp.trip_id
INNER JOIN stops          s  ON s.id  = vp.stop_id
INNER JOIN train_statuses ts ON ts.id = vp.status_id;


-- v_gold_time_updates: delay analysis — predicted vs. scheduled arrival
CREATE OR REPLACE VIEW v_gold_time_updates AS
SELECT
    tu.id,
    tu.recorded_at,
    r.name                              AS route,
    r.route_color,
    r.text_color,
    t.name                              AS trip_name,
    s.name                              AS stop_code,
    s.stop_name,
    s.stop_lat,
    s.stop_lon,
    CASE tu.direction_id
        WHEN 0 THEN 'N'
        WHEN 1 THEN 'S'
    END                                 AS direction,
    CASE EXTRACT(DOW FROM TO_DATE(tu.start_date, 'YYYYMMDD'))
        WHEN 0 THEN 'Sunday'
        WHEN 6 THEN 'Saturday'
        ELSE        'Weekday'
    END                                 AS service_day,
    TO_TIMESTAMP(tu.arrival_time)       AS predicted_arrival,
    TO_TIMESTAMP(tu.departure_time)     AS predicted_departure,
    sched.scheduled_arrival,
    EXTRACT(EPOCH FROM (
        TO_TIMESTAMP(tu.arrival_time)
        - (TO_DATE(tu.start_date, 'YYYYMMDD') + sched.scheduled_arrival::INTERVAL)
    ))::INTEGER                         AS delay_seconds,
    CASE
        WHEN EXTRACT(EPOCH FROM (
            TO_TIMESTAMP(tu.arrival_time)
            - (TO_DATE(tu.start_date, 'YYYYMMDD') + sched.scheduled_arrival::INTERVAL)
        )) > 300 THEN 'DELAYED'
        ELSE 'ON_TIME'
    END                                 AS trip_status
FROM time_updates tu
INNER JOIN routes r ON r.id = tu.route_id
INNER JOIN trips  t ON t.id = tu.trip_id
INNER JOIN stops  s ON s.id = tu.stop_id
LEFT JOIN LATERAL (
    SELECT st.arrival_time AS scheduled_arrival
    FROM stop_times st
    INNER JOIN scheduled_trips strp ON strp.trip_id = st.trip_id
    INNER JOIN calendar       cal  ON cal.service_id = strp.service_id
    WHERE st.stop_id       = s.name
      AND strp.route_id    = r.name
      AND strp.direction_id = tu.direction_id
      AND (
          (EXTRACT(DOW FROM TO_DATE(tu.start_date, 'YYYYMMDD')) BETWEEN 1 AND 5 AND cal.monday = 1)
       OR (EXTRACT(DOW FROM TO_DATE(tu.start_date, 'YYYYMMDD')) = 6 AND cal.saturday = 1)
       OR (EXTRACT(DOW FROM TO_DATE(tu.start_date, 'YYYYMMDD')) = 0 AND cal.sunday = 1)
      )
    ORDER BY ABS(
        EXTRACT(EPOCH FROM (st.arrival_time::INTERVAL))
        - EXTRACT(EPOCH FROM (
            TO_TIMESTAMP(tu.arrival_time) - TO_DATE(tu.start_date, 'YYYYMMDD')
          ))
    )
    LIMIT 1
) sched ON TRUE;
