-- Additive and repeatable: the explicit importer may apply this before a service restart.
CREATE TABLE IF NOT EXISTS core.experiment_source_rows (
    source_id VARCHAR(160) NOT NULL REFERENCES core.sources(source_id),
    sheet_name TEXT NOT NULL DEFAULT '',
    row_number INTEGER NOT NULL,
    experiment_id VARCHAR(64) NOT NULL REFERENCES core.experiments(experiment_id),
    source_test_id TEXT NOT NULL,
    headers TEXT[] NOT NULL,
    raw_cells JSONB NOT NULL,
    original_cells JSONB,
    PRIMARY KEY (source_id, sheet_name, row_number)
);
CREATE INDEX IF NOT EXISTS idx_source_rows_experiment ON core.experiment_source_rows(experiment_id);
