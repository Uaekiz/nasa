-- Pyrosphere core data model (work package 1.1 / 1.3 / 1.4)
-- V1 was applied as an empty baseline, therefore the physical model lives in V2.

CREATE TABLE core.investigations (
    investigation_id      VARCHAR(32) PRIMARY KEY,
    name                  VARCHAR(255) NOT NULL,
    description           TEXT,
    available_data_types  TEXT[] NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE core.sources (
    source_id        VARCHAR(160) PRIMARY KEY,
    investigation_id VARCHAR(32) NOT NULL REFERENCES core.investigations (investigation_id),
    title            VARCHAR(512) NOT NULL,
    source_type      VARCHAR(16) NOT NULL,
    doi              VARCHAR(255),
    original_url     TEXT,
    document_url     TEXT,
    local_path       TEXT,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sources_investigation ON core.sources (investigation_id);

-- Persistent experiment identity. The row fingerprint makes re-imports idempotent.
CREATE TABLE core.experiments (
    experiment_id        VARCHAR(64) PRIMARY KEY,
    investigation_id     VARCHAR(32) NOT NULL REFERENCES core.investigations (investigation_id),
    source_id            VARCHAR(160) REFERENCES core.sources (source_id),
    source_test_id       VARCHAR(64),
    experiment_identifier VARCHAR(160),
    fuel                 VARCHAR(160),
    experiment_date      DATE,
    date_raw             VARCHAR(64),
    test_time            VARCHAR(32),
    reported_outcome     VARCHAR(64),
    source_row_number    INTEGER,
    row_fingerprint      CHAR(64) NOT NULL UNIQUE,
    raw_row              JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_experiments_investigation ON core.experiments (investigation_id);
CREATE INDEX idx_experiments_fuel ON core.experiments (fuel);

-- Monotonic per-investigation sequence used only when a new source row is seen.
CREATE TABLE core.experiment_id_sequence (
    investigation_id VARCHAR(32) PRIMARY KEY REFERENCES core.investigations (investigation_id),
    last_value       INTEGER NOT NULL DEFAULT 0
);

-- Conditions and measurements share one structure; category separates them in API responses.
CREATE TABLE core.experiment_measurements (
    measurement_id    BIGSERIAL PRIMARY KEY,
    experiment_id     VARCHAR(64) NOT NULL REFERENCES core.experiments (experiment_id) ON DELETE CASCADE,
    category          VARCHAR(16) NOT NULL DEFAULT 'MEASUREMENT',
    name              VARCHAR(160) NOT NULL,
    value             DOUBLE PRECISION,
    unit              VARCHAR(32),
    qualifier         VARCHAR(16) NOT NULL DEFAULT 'UNKNOWN',
    start_value       DOUBLE PRECISION,
    end_value         DOUBLE PRECISION,
    min_value         DOUBLE PRECISION,
    max_value         DOUBLE PRECISION,
    raw_value         TEXT,
    missing_reason    VARCHAR(64),
    quality_status    VARCHAR(16) NOT NULL DEFAULT 'MISSING',
    source_id         VARCHAR(160),
    original_value    DOUBLE PRECISION,
    original_unit     VARCHAR(32),
    conversion_method VARCHAR(64),
    display_order     INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT chk_measurement_category CHECK (category IN ('CONDITION', 'MEASUREMENT')),
    CONSTRAINT chk_measurement_qualifier CHECK (qualifier IN ('EXACT', 'APPROXIMATE', 'GREATER_THAN', 'LESS_THAN', 'RANGE', 'CHANGING', 'UNKNOWN')),
    CONSTRAINT chk_measurement_quality CHECK (quality_status IN ('VERIFIED', 'REQUIRES_REVIEW', 'MISSING'))
);

CREATE INDEX idx_measurements_experiment ON core.experiment_measurements (experiment_id);
CREATE INDEX idx_measurements_name ON core.experiment_measurements (name);

CREATE TABLE core.reported_findings (
    finding_id    BIGSERIAL PRIMARY KEY,
    experiment_id VARCHAR(64) NOT NULL REFERENCES core.experiments (experiment_id) ON DELETE CASCADE,
    name          VARCHAR(160) NOT NULL,
    value         TEXT,
    raw_value     TEXT,
    source_id     VARCHAR(160),
    display_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_findings_experiment ON core.reported_findings (experiment_id);

CREATE TABLE core.experiment_warnings (
    warning_id    BIGSERIAL PRIMARY KEY,
    experiment_id VARCHAR(64) NOT NULL REFERENCES core.experiments (experiment_id) ON DELETE CASCADE,
    code          VARCHAR(64) NOT NULL,
    message       TEXT NOT NULL
);

CREATE INDEX idx_warnings_experiment ON core.experiment_warnings (experiment_id);
