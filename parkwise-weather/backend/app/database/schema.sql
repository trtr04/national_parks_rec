-- =====================================================================
-- ParkWise Weather — PostgreSQL schema
-- Mirrors app/database/models.py. Safe to run repeatedly (IF NOT EXISTS).
--
-- Run against Neon or local Postgres:
--     psql "$DATABASE_URL" -f backend/app/database/schema.sql
--
-- For local SQLite development you don't need this file: the API creates
-- the same tables automatically on startup (scripts/init_db.py does too).
--
-- Units: °C, mm (precipitation, rainfall), cm (snowfall), km/h (wind).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. parks — one row per officially designated National Park
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parks (
    park_code              VARCHAR(10)      PRIMARY KEY,          -- NPS code, e.g. 'yose'
    park_name              VARCHAR(200)     NOT NULL,
    state                  VARCHAR(50)      NOT NULL,             -- may be 'CA,NV'
    latitude               DOUBLE PRECISION NOT NULL,
    longitude              DOUBLE PRECISION NOT NULL,
    description            TEXT,
    weather_location_note  TEXT,                                  -- which point the weather represents
    data_source            VARCHAR(30)      NOT NULL DEFAULT 'nps_api',
    updated_at             TIMESTAMPTZ               DEFAULT now(),
    CONSTRAINT ck_parks_latitude  CHECK (latitude  BETWEEN -90  AND 90),
    CONSTRAINT ck_parks_longitude CHECK (longitude BETWEEN -180 AND 180)
);

-- ---------------------------------------------------------------------
-- 2. weather_history — one row per park per day (Open-Meteo archive)
--    Composite PK (park_code, date) guarantees no duplicate days, so the
--    ETL can use INSERT ... ON CONFLICT DO NOTHING / DO UPDATE safely.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather_history (
    park_code       VARCHAR(10) NOT NULL REFERENCES parks(park_code) ON DELETE CASCADE,
    date            DATE        NOT NULL,
    temp_max        DOUBLE PRECISION,
    temp_min        DOUBLE PRECISION,
    precipitation   DOUBLE PRECISION,
    rainfall        DOUBLE PRECISION,
    snowfall        DOUBLE PRECISION,
    wind_speed_max  DOUBLE PRECISION,
    PRIMARY KEY (park_code, date),
    CONSTRAINT ck_wh_precip_nonneg CHECK (precipitation  IS NULL OR precipitation  >= 0),
    CONSTRAINT ck_wh_rain_nonneg   CHECK (rainfall       IS NULL OR rainfall       >= 0),
    CONSTRAINT ck_wh_snow_nonneg   CHECK (snowfall       IS NULL OR snowfall       >= 0),
    CONSTRAINT ck_wh_wind_nonneg   CHECK (wind_speed_max IS NULL OR wind_speed_max >= 0),
    CONSTRAINT ck_wh_temp_order    CHECK (temp_min IS NULL OR temp_max IS NULL OR temp_min <= temp_max)
);

-- PK covers lookups by (park_code, date). This index covers "all parks on/around a date".
CREATE INDEX IF NOT EXISTS ix_weather_history_date ON weather_history (date);

-- ---------------------------------------------------------------------
-- 3. weather_predictions — log of every prediction served (Phase 3+)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather_predictions (
    prediction_id              SERIAL       PRIMARY KEY,
    park_code                  VARCHAR(10)  NOT NULL REFERENCES parks(park_code) ON DELETE CASCADE,
    target_date                DATE         NOT NULL,
    prediction_generated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    prediction_type            VARCHAR(20)  NOT NULL,
    model_name                 VARCHAR(60)  NOT NULL,
    activity                   VARCHAR(30),
    predicted_temp_max         DOUBLE PRECISION,
    predicted_temp_min         DOUBLE PRECISION,
    precipitation_probability  DOUBLE PRECISION,   -- 0.0–1.0
    weather_suitability_score  DOUBLE PRECISION,   -- 0–100
    CONSTRAINT ck_wp_prediction_type   CHECK (prediction_type IN ('forecast', 'climate_estimate')),
    CONSTRAINT ck_wp_precip_prob_range CHECK (precipitation_probability IS NULL
                                              OR precipitation_probability BETWEEN 0 AND 1),
    CONSTRAINT ck_wp_score_range       CHECK (weather_suitability_score IS NULL
                                              OR weather_suitability_score BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS ix_weather_predictions_park_target
    ON weather_predictions (park_code, target_date);

-- ---------------------------------------------------------------------
-- 4. park_features — what each park offers, for the park recommender
--    Filled by scripts/load_park_features.py from the NPS API. Topics and
--    activities keep NPS's own names; the recommender maps them to the
--    scenery and wildlife choices users see.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS park_features (
    park_code                 VARCHAR(10)  PRIMARY KEY REFERENCES parks(park_code) ON DELETE CASCADE,
    topics                    JSON         NOT NULL,   -- list of NPS topic names
    activities                JSON         NOT NULL,   -- list of NPS activity names
    campground_count          INTEGER      NOT NULL DEFAULT 0,
    campgrounds_with_showers  INTEGER      NOT NULL DEFAULT 0,
    campground_open_months    JSON,                    -- 12 counts, Jan first: campgrounds open most of each month
    visitor_center_count      INTEGER,                 -- NULL = not loaded
    vehicle_fee_usd           DOUBLE PRECISION,        -- NULL = NPS lists no private-vehicle fee
    nps_url                   VARCHAR(300),
    image_url                 VARCHAR(500),
    image_alt                 TEXT,
    image_credit              VARCHAR(300),
    updated_at                TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT ck_pf_campgrounds_nonneg CHECK (campground_count >= 0)
);
