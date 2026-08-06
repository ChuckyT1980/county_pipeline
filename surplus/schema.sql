-- Surplus recovery schema. Sits alongside verification.sqlite as a separate
-- concern (different product, different data). If we want joined queries
-- later we can ATTACH DATABASE both.

-- One row per (county, apn, deed_date) — the fundamental unit of a claimable
-- surplus opportunity. Deduped on ingest so re-scraping the same county
-- doesn't create dupes.
CREATE TABLE IF NOT EXISTS surplus_opportunities (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    county                TEXT NOT NULL,
    apn                   TEXT NOT NULL,
    former_owner_raw      TEXT,                -- as printed on the county list
    former_owner_canonical TEXT,               -- normalized for skip-trace + graph lookup
    surplus_amount        REAL,
    min_bid               REAL,
    sale_price            REAL,
    sale_date             TEXT,
    deed_date             TEXT,                -- trustee's deed recording date (claim clock start)
    claim_deadline_at     TEXT,                -- deed_date + 1 year
    party_of_interest     TEXT,                -- sometimes listed separately (lienholders)
    lienholders           TEXT,                -- JSON list of any known senior lienholders

    -- Source provenance
    source_url            TEXT,
    source_snapshot_path  TEXT,                -- path to downloaded PDF/HTML for audit
    source_first_seen     TEXT,                -- ISO timestamp
    source_last_seen      TEXT,

    -- Lifecycle
    status                TEXT DEFAULT 'open', -- open / traced / mailed / signed / filed / paid / expired / disqualified
    disqualification_reason TEXT,

    -- Skip trace linkage
    last_traced_at        TEXT,
    trace_cost_cents      INTEGER DEFAULT 0,

    -- Outreach state
    first_mailed_at       TEXT,
    last_mailed_at        TEXT,
    contract_signed_at    TEXT,
    claim_filed_at        TEXT,
    payment_received_at   TEXT,
    payment_amount        REAL,
    our_fee_amount        REAL,
    contingency_pct       REAL,

    ingested_at           TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    UNIQUE(county, apn, deed_date)
);
CREATE INDEX IF NOT EXISTS idx_surplus_county ON surplus_opportunities(county);
CREATE INDEX IF NOT EXISTS idx_surplus_deadline ON surplus_opportunities(claim_deadline_at);
CREATE INDEX IF NOT EXISTS idx_surplus_status ON surplus_opportunities(status);
CREATE INDEX IF NOT EXISTS idx_surplus_owner ON surplus_opportunities(former_owner_canonical);

-- Skip trace results. Keyed by canonical name + last-known address so we
-- don't re-trace the same person across multiple parcels.
CREATE TABLE IF NOT EXISTS skip_trace_results (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name        TEXT NOT NULL,
    last_known_address    TEXT,
    provider              TEXT NOT NULL,        -- e.g. "batchskiptracing", "whitepages_pro", "stub", "manual"
    request_at            TEXT NOT NULL,

    -- Returned data
    current_address       TEXT,
    current_city_state    TEXT,
    phones_json           TEXT,                 -- JSON array of {number, type, confidence}
    emails_json           TEXT,                 -- JSON array of emails
    relatives_json        TEXT,                 -- JSON array of {name, relation, age}
    age                   INTEGER,
    is_deceased           INTEGER DEFAULT 0,    -- 0/1
    date_of_death         TEXT,
    confidence            REAL,                 -- 0..1 overall confidence

    -- Cost tracking
    cost_cents            INTEGER DEFAULT 0,

    -- Raw payload (for debugging or re-parsing)
    raw_response_json     TEXT,

    UNIQUE(canonical_name, last_known_address, provider)
);
CREATE INDEX IF NOT EXISTS idx_trace_name ON skip_trace_results(canonical_name);

-- Ledger of every skip trace attempt (even duplicates). For cost analytics.
CREATE TABLE IF NOT EXISTS skip_trace_ledger (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    surplus_id            INTEGER REFERENCES surplus_opportunities(id),
    canonical_name        TEXT NOT NULL,
    provider              TEXT NOT NULL,
    cost_cents            INTEGER DEFAULT 0,
    hit                   INTEGER DEFAULT 0,    -- 1 if result had any usable contact info
    requested_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_surplus ON skip_trace_ledger(surplus_id);

-- Outreach tracking. One row per attempted contact (mail, phone, email).
CREATE TABLE IF NOT EXISTS outreach_events (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    surplus_id            INTEGER NOT NULL REFERENCES surplus_opportunities(id),
    channel               TEXT NOT NULL,        -- mail / phone / email / cert_mail
    contact_used          TEXT,                 -- the specific phone/address contacted
    outcome               TEXT,                 -- sent / delivered / returned / no_answer / voicemail / interested / not_interested / signed
    notes                 TEXT,
    sent_at               TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outreach_surplus ON outreach_events(surplus_id);

-- County config: metadata about each source we scrape. Populated on ingest.
CREATE TABLE IF NOT EXISTS county_sources (
    county                TEXT PRIMARY KEY,
    display_name          TEXT,
    ttc_url               TEXT,                 -- treasurer-tax-collector page
    excess_proceeds_url   TEXT,                 -- the actual list URL
    format                TEXT,                 -- pdf / html_table / interactive
    processing_cadence    TEXT,                 -- rolling / monthly / quarterly / annual
    fee_cap_pct           REAL,                 -- if county caps contingency fee
    notes                 TEXT,
    last_scraped_at       TEXT,
    last_scrape_count     INTEGER
);

-- Unclaimed estates (Public Administrator / decedent estates with unlocated
-- or unknown heirs). Different data shape from tax-sale surplus, so a
-- separate table — but shares skip_trace_results + outreach_events for
-- the recovery workflow.
CREATE TABLE IF NOT EXISTS unclaimed_estates (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    county                TEXT NOT NULL,
    pool_type             TEXT NOT NULL,        -- 'unlocated_heirs' / 'unknown_heirs' / 'tax_refund'

    decedent_name         TEXT,                 -- Charles E Smith
    decedent_canonical    TEXT,                 -- SMITH CHARLES E (for graph joins)
    date_of_death         TEXT,                 -- ISO YYYY-MM-DD
    amount                REAL,

    identified_heir       TEXT,                 -- populated for pool_type='unlocated_heirs'
    identified_heir_canonical TEXT,
    probate_case_no       TEXT,                 -- county probate case number
    date_in               TEXT,                 -- when funds came into county treasury
    escheat_date          TEXT,                 -- date_in + 3 years (per CGC §50050)

    -- Source
    source_url            TEXT,
    source_snapshot_path  TEXT,
    source_first_seen     TEXT,
    source_last_seen      TEXT,

    -- Lifecycle (same states as surplus)
    status                TEXT DEFAULT 'open',  -- open / traced / mailed / signed / filed / paid / expired
    disqualification_reason TEXT,
    last_traced_at        TEXT,
    trace_cost_cents      INTEGER DEFAULT 0,
    first_mailed_at       TEXT,
    contract_signed_at    TEXT,
    claim_filed_at        TEXT,
    payment_received_at   TEXT,
    payment_amount        REAL,
    our_fee_amount        REAL,

    ingested_at           TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    UNIQUE(county, pool_type, decedent_name, date_of_death)
);
CREATE INDEX IF NOT EXISTS idx_estates_county ON unclaimed_estates(county);
CREATE INDEX IF NOT EXISTS idx_estates_escheat ON unclaimed_estates(escheat_date);
CREATE INDEX IF NOT EXISTS idx_estates_status ON unclaimed_estates(status);
CREATE INDEX IF NOT EXISTS idx_estates_decedent ON unclaimed_estates(decedent_canonical);
CREATE INDEX IF NOT EXISTS idx_estates_heir ON unclaimed_estates(identified_heir_canonical);

-- Cross-references: when a decedent's name appears in the recorder graph
-- (i.e. they owned property) OR appears on a tax auction / surplus list,
-- log the match here so we can compound-claim across pools.
CREATE TABLE IF NOT EXISTS estate_crossrefs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    estate_id             INTEGER NOT NULL REFERENCES unclaimed_estates(id),
    match_kind            TEXT NOT NULL,        -- 'auction_parcel_owner' / 'surplus_former_owner' / 'recorder_graph_actor'
    matched_entity_kind   TEXT,                 -- 'parcel' / 'surplus_opportunity' / 'graph_node'
    matched_entity_id     TEXT,                 -- APN / surplus_id / graph_node_id
    matched_at            TEXT NOT NULL,
    notes                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_estcx_estate ON estate_crossrefs(estate_id);
