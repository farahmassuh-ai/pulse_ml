-- One row per bus stop event, from two sources:
--   'historical' = MBTA Bus Arrival/Departure files (have an actual time)
--   'api'        = daily /schedules pull (planned service, actual is NULL)
CREATE TABLE IF NOT EXISTS stop_events (
    id                 BIGSERIAL  PRIMARY KEY,
    service_date       DATE       NOT NULL,
    route_id           TEXT       NOT NULL,   -- file-style id: '01', 'SL1', 'CT2'
    direction_id       TEXT       NOT NULL,   -- 'Inbound' / 'Outbound'
    half_trip_id       TEXT,
    stop_id            TEXT       NOT NULL,
    time_point_id      TEXT,
    time_point_order   INTEGER,
    point_type         TEXT,                  -- Startpoint / Midpoint / Endpoint
    standard_type      TEXT,                  -- Headway / Schedule
    scheduled          TIMESTAMP  NOT NULL,   -- Boston wall-clock time, no time zone
    scheduled_headway  INTEGER,               -- seconds
    actual             TIMESTAMP,             -- NULL when the bus has no recorded/known actual
    delay_min          REAL,                  -- actual - scheduled, in minutes
    late               BOOLEAN,               -- delay_min > 3; NULL when actual is NULL
    source             TEXT       NOT NULL DEFAULT 'historical',
    UNIQUE (service_date, route_id, direction_id, stop_id, scheduled)
);
