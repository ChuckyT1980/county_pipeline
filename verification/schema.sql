-- verification.sqlite schema
--
-- Substrate for the multi-layer verification system. Every pipeline stage
-- writes provenance + flags here so the shipped CSV can carry per-field
-- confidence and the graph layer (Phase 3) can reason across parcels.
--
-- Layer roadmap:
--   0. Substrate (this file) — provenance, flags, run tracking
--   1. Completeness — did we pull every source we expected to
--   2. Consistency — does what we pulled agree with itself
--   3. Graph — cross-parcel actor network
--   4. Ownership — is our identified owner really the current owner
--   5. Outcome — post-auction feedback into scoring
--
-- Tables are designed once and populated incrementally. No migrations
-- planned between phases.

-- One row per pipeline cycle per county. Everything else joins to this.
CREATE TABLE IF NOT EXISTS verification_runs (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at               TEXT NOT NULL,
    finished_at              TEXT,
    county                   TEXT NOT NULL,
    cycle_label              TEXT,                 -- e.g. "Aug 2026 primary auction"
    pipeline_version         TEXT,
    input_source             TEXT,                 -- e.g. path to source CSV
    parcel_count             INTEGER,
    completeness_avg         REAL,
    consistency_avg          REAL,
    ownership_confidence_avg REAL,
    status                   TEXT DEFAULT 'in_progress'  -- in_progress / completed / failed
);
CREATE INDEX IF NOT EXISTS idx_runs_county_started ON verification_runs(county, started_at);

-- One row per parcel per run. Rolls up the field-level provenance below.
CREATE TABLE IF NOT EXISTS parcel_verifications (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                   INTEGER NOT NULL REFERENCES verification_runs(id),
    apn                      TEXT NOT NULL,
    county                   TEXT NOT NULL,
    completeness_score       REAL,                 -- 0..100
    consistency_score        REAL,                 -- 0..100
    ownership_confidence     REAL,                 -- 0..1
    ownership_class          TEXT,                 -- INDIVIDUAL/TRUST/ESTATE/LLC/CORP/UNKNOWN
    ownership_flags          TEXT,                 -- JSON list, e.g. ["recent_transfer","trust_involved"]
    sources_expected         TEXT,                 -- JSON list of source ids
    sources_succeeded        TEXT,                 -- JSON list of source ids
    verified_at              TEXT,
    UNIQUE(run_id, apn)
);
CREATE INDEX IF NOT EXISTS idx_pv_apn ON parcel_verifications(county, apn);

-- Per-field provenance. Every value a stage writes to the CSV should have a row here.
-- Enables "owner_name came from recorder_grantee with confidence 0.9" claims in the deliverable.
CREATE TABLE IF NOT EXISTS field_provenance (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                   INTEGER NOT NULL REFERENCES verification_runs(id),
    apn                      TEXT NOT NULL,
    field_name               TEXT NOT NULL,        -- e.g. "owner_name", "mailing_address", "situs_address"
    field_value              TEXT,
    source                   TEXT NOT NULL,        -- e.g. "recorder_chain_grantee", "asr_assessee", "taxbill_v2"
    confidence               REAL NOT NULL,        -- 0..1
    fetched_at               TEXT NOT NULL,
    notes                    TEXT
);
CREATE INDEX IF NOT EXISTS idx_fp_apn_field ON field_provenance(apn, field_name);
CREATE INDEX IF NOT EXISTS idx_fp_run ON field_provenance(run_id);

-- Verification flags: things that failed a check.
-- Populated by Layers 1, 2, 4 as they come online.
CREATE TABLE IF NOT EXISTS verification_flags (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                   INTEGER NOT NULL REFERENCES verification_runs(id),
    apn                      TEXT NOT NULL,
    layer                    TEXT NOT NULL,        -- completeness / consistency / ownership / outcome
    flag_code                TEXT NOT NULL,        -- e.g. "MISSING_RECORDER_CHAIN"
    severity                 TEXT NOT NULL,        -- info / warn / error
    message                  TEXT,
    created_at               TEXT NOT NULL,
    resolved_at              TEXT,
    resolved_by              TEXT                  -- "manual" / "automatic" / actor name
);
CREATE INDEX IF NOT EXISTS idx_flags_apn ON verification_flags(apn);
CREATE INDEX IF NOT EXISTS idx_flags_run_severity ON verification_flags(run_id, severity);

-- Graph nodes: people, entities, parcels, docs.
-- Populated by Phase 3 (graph). Empty until then; safe to query as UNION with empty results.
CREATE TABLE IF NOT EXISTS graph_nodes (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    node_kind                TEXT NOT NULL,        -- person / entity / parcel / doc
    canonical_name           TEXT,                 -- normalized name (uppercase, punctuation-stripped)
    display_name             TEXT,                 -- original for UI
    apn                      TEXT,                 -- populated for parcel nodes
    doc_number               TEXT,                 -- populated for doc nodes
    county                   TEXT,
    first_seen               TEXT,
    last_seen                TEXT,
    extra_json               TEXT                  -- misc metadata (LLC officers, doc type, etc.)
);
CREATE INDEX IF NOT EXISTS idx_nodes_kind_canonical ON graph_nodes(node_kind, canonical_name);
CREATE INDEX IF NOT EXISTS idx_nodes_apn ON graph_nodes(apn);
CREATE INDEX IF NOT EXISTS idx_nodes_doc ON graph_nodes(doc_number);

-- Graph edges: typed relationships between nodes.
-- e.g. person --grantor--> doc --affects--> parcel
CREATE TABLE IF NOT EXISTS graph_edges (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id             INTEGER NOT NULL REFERENCES graph_nodes(id),
    to_node_id               INTEGER NOT NULL REFERENCES graph_nodes(id),
    edge_kind                TEXT NOT NULL,        -- grantor/grantee/trustee/beneficiary/attorney/notary/affects/references/neighbor/officer_of
    doc_id                   INTEGER REFERENCES graph_nodes(id),  -- doc node this edge originated from (nullable for derived edges)
    weight                   REAL DEFAULT 1.0,
    first_seen               TEXT,
    last_seen                TEXT
);
CREATE INDEX IF NOT EXISTS idx_edges_from ON graph_edges(from_node_id, edge_kind);
CREATE INDEX IF NOT EXISTS idx_edges_to ON graph_edges(to_node_id, edge_kind);

-- Post-auction outcomes. Populated by Phase 5.
-- Fed by Trustee's Deed Upon Sale extraction after each auction date.
CREATE TABLE IF NOT EXISTS auction_outcomes (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    apn                      TEXT NOT NULL,
    county                   TEXT NOT NULL,
    auction_label            TEXT,                 -- e.g. "August 2026 primary"
    auction_date             TEXT,
    outcome_class            TEXT,                 -- SOLD / REDEEMED / UNSOLD / WITHDRAWN
    sale_price               REAL,
    buyer_name               TEXT,
    buyer_canonical_name     TEXT,                 -- for graph join
    trustees_deed_number     TEXT,
    trustees_deed_date       TEXT,
    predicted_priority_score REAL,                 -- what we scored it as
    calibration_delta        REAL,                 -- for regression signal
    recorded_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcomes_apn ON auction_outcomes(county, apn);
CREATE INDEX IF NOT EXISTS idx_outcomes_auction ON auction_outcomes(county, auction_label);

-- Score calibration snapshots. Populated by Phase 5 when outcomes feed back into scoring.
CREATE TABLE IF NOT EXISTS score_calibration (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    calibrated_at            TEXT NOT NULL,
    county                   TEXT,
    sample_size              INTEGER,
    formula_before           TEXT,
    formula_after            TEXT,
    r_squared_before         REAL,
    r_squared_after          REAL,
    notes                    TEXT
);

-- Adjacent-source config: what external data sources exist per county, and which are enabled.
-- Populated once, referenced by Layer 1 to compute expected_sources.
CREATE TABLE IF NOT EXISTS adjacent_sources (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id                TEXT NOT NULL UNIQUE, -- e.g. "asr_print", "taxbill_v2", "recorder_chain", "ca_sos", "fema_flood"
    county                   TEXT,                 -- NULL = applies to all counties
    display_name             TEXT NOT NULL,
    kind                     TEXT NOT NULL,       -- assessor/tax/recorder/court/environmental/entity/skiptrace/other
    enabled                  INTEGER DEFAULT 1,
    cost_per_lookup          REAL DEFAULT 0.0,
    notes                    TEXT
);

-- Seed the adjacent sources table with what Phase 0 knows about
INSERT OR IGNORE INTO adjacent_sources (source_id, county, display_name, kind, enabled, cost_per_lookup, notes) VALUES
    ('asr_print',        NULL, 'MBAP AsrPrint (assessor)',            'assessor',      1, 0.0, 'Wired in stage4_owner_enrich'),
    ('taxbill_v2',       NULL, 'MPTS TaxBill v2 (tax collector)',     'tax',           1, 0.0, 'Wired in stage4_owner_enrich'),
    ('mbc_tax_detail',   NULL, 'MPTS/MBC tax detail page',            'tax',           1, 0.0, 'Wired in ButteTaxClient / stage2_verify'),
    ('recorder_chain',   NULL, 'Tyler EagleWeb recorder chain (single doc)',  'recorder', 1, 0.0, 'Currently pulls only the doc# from tax page; Layer 1 will expand to full chain'),
    ('recorder_full',    NULL, 'Tyler EagleWeb full APN chain + all actors',  'recorder', 0, 0.0, 'Phase 1: not yet enabled'),
    ('ca_sos_bizfile',   NULL, 'CA Secretary of State entity lookup', 'entity',        0, 0.0, 'Phase 1: LLC/corp officer + status lookup'),
    ('fema_flood',       NULL, 'FEMA flood hazard zone',              'environmental', 0, 0.0, 'Phase 1: free federal API'),
    ('calfire_hazard',   NULL, 'Cal Fire severity hazard zone',       'environmental', 0, 0.0, 'Phase 1: free state API'),
    ('batch_skip_trace', NULL, 'BatchSkipTracing (phones+emails)',    'skiptrace',     0, 0.20, 'Phase 3+: paid API'),
    ('pacer',            NULL, 'PACER (federal court records)',       'court',         0, 0.10, 'Future: bankruptcy filings'),
    ('court_superior',   NULL, 'County superior court (probate/divorce)', 'court',     0, 0.0, 'Future: per-county scraper'),
    ('code_enforcement', NULL, 'County code enforcement violations',  'other',         0, 0.0, 'Future: per-county portal');
