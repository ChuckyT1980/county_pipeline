-- property_intelligence_v2 - migration 001: initial schema (Phase 1).
--
-- This is the ONE canonical, versioned schema for property_intelligence_v2.
-- There is no separate production schema and test schema - tests apply
-- this exact file to a temporary/in-memory SQLite database and insert
-- only clearly labeled TEST_ONLY fixture rows (see
-- property_intelligence_v2/tests/test_schema.py).
--
-- Implements the nine contracts/entities.py dataclasses as tables, in
-- pipeline order:
--   source_registry -> ingestion_runs -> raw_evidence -> observations
--   -> parcels -> parcel_matches -> canonical_property_state
--   -> reconciliation_feedback -> exceptions
--
-- Storage convention: raw sqlite3, hand-written DDL, no ORM - matching
-- the legacy repository's existing surplus.sqlite / verification.sqlite
-- (also raw sqlite3 with hand-written DDL). No ORM is introduced here
-- since the repository doesn't already have one.
--
-- SQLite -> PostgreSQL portability notes (kept deliberately simple so a
-- later port is mechanical, not a rewrite):
--   - TEXT is used for all timestamps (ISO 8601 strings), not a SQLite-
--     specific date type - maps directly to Postgres TIMESTAMPTZ later.
--   - TEXT primary/foreign keys throughout (app-generated ids), not
--     SQLite's AUTOINCREMENT - maps directly to Postgres TEXT/UUID.
--   - CHECK (col IN (...)) for every controlled-vocabulary column - the
--     same constraint syntax is valid in Postgres unchanged.
--   - JSON stored as TEXT (SQLite has no native JSON type) - maps to
--     Postgres JSONB later with a column-type change only, no data
--     reshaping.
--   - No SQLite-only pragmas or functions used inside the DDL itself
--     (PRAGMA foreign_keys is a connection-level setting, issued by the
--     application/test at connect time, not part of this file).
--
-- Applying this file creates empty tables only. No data is inserted by
-- this file, and no real or synthetic California county evidence may be
-- ingested in Phase 1 - raw_evidence stores paths and hashes as metadata
-- only, never actual evidence content.

CREATE TABLE schema_migrations (
    version         INTEGER PRIMARY KEY,
    applied_at      TEXT NOT NULL,
    description     TEXT NOT NULL
);

-- ── source_registry ─────────────────────────────────────────────────────
-- What sources exist, per county. One row per (county, source_type, name) -
-- a county can have more than one source of the same type (e.g. two
-- different recorder-search modes with different capability levels).
CREATE TABLE source_registry (
    source_id       TEXT PRIMARY KEY,
    county          TEXT NOT NULL,
    county_fips     TEXT NOT NULL,
    source_type     TEXT NOT NULL CHECK (source_type IN
                     ('assessor', 'recorder', 'tax_collector', 'auction_platform', 'gis', 'other')),
    name            TEXT NOT NULL,
    base_url        TEXT,
    access_level    TEXT NOT NULL CHECK (access_level IN
                     ('full', 'index_only', 'manual_only', 'blocked', 'unknown')),
    registered_at       TEXT NOT NULL,
    last_verified_at    TEXT,
    reliability_notes   TEXT
);
CREATE INDEX idx_source_registry_county ON source_registry(county);

-- ── ingestion_runs ──────────────────────────────────────────────────────
-- One row per attempt to pull from a source. Created at the START of an
-- attempt, before success/failure is known - a failed run is a completed,
-- valid row, never a missing one (attempt -> observe -> classify -> save
-- evidence -> record outcome -> choose next action).
CREATE TABLE ingestion_runs (
    run_id          TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES source_registry(source_id),
    started_at      TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN
                     ('attempted', 'in_progress', 'succeeded', 'partial', 'failed', 'quarantined')),
    finished_at         TEXT,
    attempted_count     INTEGER,
    succeeded_count     INTEGER,
    failed_count        INTEGER,
    next_action         TEXT NOT NULL DEFAULT 'none' CHECK (next_action IN
                         ('retry', 'fallback', 'quarantine', 'human_review', 'none')),
    notes               TEXT
);
CREATE INDEX idx_ingestion_runs_source ON ingestion_runs(source_id);
CREATE INDEX idx_ingestion_runs_status ON ingestion_runs(status);

-- ── raw_evidence ────────────────────────────────────────────────────────
-- METADATA ONLY: storage_path/content_hash describe where an artifact
-- would live and its integrity hash - this table never stores actual
-- evidence content (HTML/PDF bytes, parsed text, etc.). Immutable by
-- contract (see contracts/entities.py) - not yet enforced by a DB
-- trigger in Phase 1 (SQLite triggers could add that later if a real
-- backend is stood up); enforced by application code and tests for now.
CREATE TABLE raw_evidence (
    evidence_id             TEXT PRIMARY KEY,
    ingestion_run_id        TEXT NOT NULL REFERENCES ingestion_runs(run_id),
    source_id               TEXT NOT NULL REFERENCES source_registry(source_id),
    retrieved_at            TEXT NOT NULL,
    content_hash            TEXT NOT NULL,
    content_type            TEXT NOT NULL,
    source_url_or_identifier TEXT NOT NULL,
    storage_path            TEXT,
    immutable               INTEGER NOT NULL DEFAULT 1 CHECK (immutable IN (0, 1))
);
CREATE INDEX idx_raw_evidence_run ON raw_evidence(ingestion_run_id);
CREATE INDEX idx_raw_evidence_hash ON raw_evidence(content_hash);

-- ── observations ────────────────────────────────────────────────────────
-- One atomic, immutable (field_name, field_value) fact extracted from a
-- raw_evidence row. Corrections are new rows linked via
-- superseded_by_observation_id, never in-place edits.
CREATE TABLE observations (
    observation_id              TEXT PRIMARY KEY,
    evidence_id                 TEXT NOT NULL REFERENCES raw_evidence(evidence_id),
    observed_at                 TEXT NOT NULL,
    county                      TEXT NOT NULL,
    source_identifier_type      TEXT NOT NULL,
    source_identifier_value     TEXT NOT NULL,
    field_name                  TEXT NOT NULL,
    field_value                 TEXT NOT NULL,
    confidence                  TEXT NOT NULL CHECK (confidence IN
                                 ('confirmed', 'carried_forward', 'source_list_only', 'unconfirmed')),
    superseded_by_observation_id TEXT REFERENCES observations(observation_id),
    immutable                   INTEGER NOT NULL DEFAULT 1 CHECK (immutable IN (0, 1))
);
CREATE INDEX idx_observations_evidence ON observations(evidence_id);
CREATE INDEX idx_observations_identifier ON observations(source_identifier_type, source_identifier_value);
CREATE INDEX idx_observations_county ON observations(county);

-- ── parcels (Parcel Master) ─────────────────────────────────────────────
-- Deliberately bare identity - no county-specific identifier (APN, ATN,
-- or otherwise) lives here. That conflation is exactly what caused the
-- legacy pipeline's Kern ATN-labeled-as-APN defect. County identifiers
-- live in observations and connect to a parcel only via parcel_matches.
CREATE TABLE parcels (
    parcel_id               TEXT PRIMARY KEY,
    county                  TEXT NOT NULL,
    county_fips              TEXT NOT NULL,
    created_at                TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'active' CHECK (status IN
                                 ('active', 'merged', 'split', 'retired')),
    merged_into_parcel_id          TEXT REFERENCES parcels(parcel_id),
    notes                             TEXT
);
CREATE INDEX idx_parcels_county ON parcels(county);

-- ── parcel_matches ──────────────────────────────────────────────────────
-- Links one observation to one parcel. parcel_id is nullable: an
-- observation with no confirmed match yet is a valid, expected state,
-- not an error.
CREATE TABLE parcel_matches (
    match_id            TEXT PRIMARY KEY,
    observation_id       TEXT NOT NULL REFERENCES observations(observation_id),
    parcel_id             TEXT REFERENCES parcels(parcel_id),
    match_method            TEXT NOT NULL CHECK (match_method IN
                             ('exact_identifier', 'fuzzy', 'human_confirmed', 'unmatched')),
    match_confidence           REAL NOT NULL CHECK (match_confidence >= 0.0 AND match_confidence <= 1.0),
    status                        TEXT NOT NULL CHECK (status IN
                                   ('pending', 'confirmed', 'rejected', 'superseded')),
    matched_at                       TEXT,
    matched_by                         TEXT
);
CREATE INDEX idx_parcel_matches_observation ON parcel_matches(observation_id);
CREATE INDEX idx_parcel_matches_parcel ON parcel_matches(parcel_id);

-- ── canonical_property_state ────────────────────────────────────────────
-- The current, versioned, reconciled best-known state of a parcel.
-- fields_json holds a JSON object keyed by field_name, each value shaped
-- like {"value", "confidence", "source_observation_ids", "last_reconciled_at"}
-- (SQLite has no native JSON/struct column type - see portability notes
-- above). A specific (parcel_id, version) row is never edited once
-- created; superseded_by_state_id points forward to a newer version.
CREATE TABLE canonical_property_state (
    state_id                TEXT PRIMARY KEY,
    parcel_id                TEXT NOT NULL REFERENCES parcels(parcel_id),
    version                    INTEGER NOT NULL,
    as_of                        TEXT NOT NULL,
    fields_json                    TEXT NOT NULL DEFAULT '{}',
    lifecycle_status                  TEXT NOT NULL DEFAULT 'draft' CHECK (lifecycle_status IN
                                       ('draft', 'reconciled', 'stale', 'contested', 'human_review_required')),
    superseded_by_state_id               TEXT REFERENCES canonical_property_state(state_id),
    UNIQUE(parcel_id, version)
);
CREATE INDEX idx_canonical_state_parcel ON canonical_property_state(parcel_id);

-- ── reconciliation_feedback ─────────────────────────────────────────────
-- The audit trail of one reconciliation event: which observations were
-- considered, what conflicts were found, how (or whether) each was
-- resolved. resolution_method='unresolved' is a legitimate, expected
-- value - not every conflict resolves automatically.
CREATE TABLE reconciliation_feedback (
    feedback_id                        TEXT PRIMARY KEY,
    canonical_property_state_id         TEXT NOT NULL REFERENCES canonical_property_state(state_id),
    observation_ids_considered_json        TEXT NOT NULL DEFAULT '[]',
    resolved_at                               TEXT NOT NULL,
    resolution_method                            TEXT NOT NULL CHECK (resolution_method IN
                                                  ('most_recent', 'highest_confidence', 'human_decided', 'unresolved')),
    conflicts_detected_json                         TEXT NOT NULL DEFAULT '[]',
    notes                                               TEXT
);
CREATE INDEX idx_reconciliation_feedback_state ON reconciliation_feedback(canonical_property_state_id);

-- ── exceptions ──────────────────────────────────────────────────────────
-- An anomaly at any stage, with an explicit classification and chosen
-- next action - the formal mechanism for "a failure is a valid output":
-- attempt -> observe -> classify -> save evidence -> record outcome ->
-- choose next action -> retry / fallback / quarantine / human_review.
CREATE TABLE exceptions (
    exception_id            TEXT PRIMARY KEY,
    occurred_at              TEXT NOT NULL,
    stage                       TEXT NOT NULL CHECK (stage IN
                                 ('ingestion', 'observation', 'matching', 'reconciliation', 'other')),
    related_entity_type            TEXT NOT NULL,
    related_entity_id                 TEXT NOT NULL,
    classification                       TEXT NOT NULL CHECK (classification IN
                                          ('transient_error', 'source_unavailable', 'data_contradiction',
                                           'schema_mismatch', 'rate_limited', 'access_blocked', 'unknown')),
    severity                                TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    next_action                                TEXT NOT NULL CHECK (next_action IN
                                                ('retry', 'fallback', 'quarantine', 'human_review', 'none')),
    status                                        TEXT NOT NULL CHECK (status IN
                                                   ('open', 'retried', 'fallback_applied', 'quarantined', 'resolved', 'escalated')),
    evidence_id                                      TEXT REFERENCES raw_evidence(evidence_id),
    notes                                               TEXT
);
CREATE INDEX idx_exceptions_stage ON exceptions(stage);
CREATE INDEX idx_exceptions_status ON exceptions(status);
CREATE INDEX idx_exceptions_related ON exceptions(related_entity_type, related_entity_id);
