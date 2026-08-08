-- property_intelligence_v2 - migration 002: integrity hardening (Phase 1).
--
-- Applies ON TOP of 001_initial_schema.sql. Responds directly to the
-- read-only architecture audit of commit d741447, which found six
-- claims made in that commit's message were unsupported by any actual
-- SQL-level enforcement or test: evidence immutability, observation
-- immutability, append-only corrections, quarantine propagation,
-- verified-state requirements, and APN/ATN technical separation.
--
-- This migration does not claim to fix every one of those gaps
-- completely - see the honesty notes inline (especially on quarantine
-- retroactivity and TEST_ONLY enforcement) and the final status table
-- in this session's response, which marks each gap PROVEN,
-- PARTIALLY_PROVEN, DEFERRED, or BLOCKED rather than claiming success
-- uniformly.

-- ═══════════════════════════════════════════════════════════════════════
-- PART A: Make raw_evidence and observations genuinely immutable at the
-- SQL level (not by Python convention, not by an unenforced flag column).
-- ═══════════════════════════════════════════════════════════════════════

-- raw_evidence: unconditional block on UPDATE and DELETE. No carve-out.
-- Quarantine (a real, necessary post-hoc status change) is deliberately
-- NOT implemented as a mutation of this table - see Part C, which adds
-- an append-only side table instead specifically so this block can be
-- absolute rather than needing a narrower "only this one column may
-- change" trigger.
CREATE TRIGGER trg_raw_evidence_no_update
BEFORE UPDATE ON raw_evidence
BEGIN
    SELECT RAISE(ABORT, 'raw_evidence is immutable: UPDATE is not permitted. Quarantine status changes go through evidence_disposition, not this table.');
END;

CREATE TRIGGER trg_raw_evidence_no_delete
BEFORE DELETE ON raw_evidence
BEGIN
    SELECT RAISE(ABORT, 'raw_evidence is immutable: DELETE is not permitted.');
END;

-- observations: same unconditional block. The old superseded_by_observation_id
-- column (migration 001) required mutating the OLD row to record a
-- correction - fundamentally incompatible with a hard immutability block,
-- so it is replaced below with a forward-referencing column on the NEW
-- row instead, set once at INSERT time and never touched again.

DROP INDEX idx_observations_identifier;

ALTER TABLE observations DROP COLUMN source_identifier_type;
ALTER TABLE observations DROP COLUMN source_identifier_value;
-- DEPRECATION: source_identifier_type/source_identifier_value (migration
-- 001) are removed, not just deprecated in a comment - leaving them
-- present alongside the new observation_identifiers table (Part B) would
-- be exactly the "two competing identifier systems without a documented
-- transition" the audit warned against. No data existed in these columns
-- (Phase 1, no real ingestion has run) so this is a clean removal, not a
-- lossy migration. All identifier data now lives exclusively in
-- observation_identifiers.

ALTER TABLE observations DROP COLUMN superseded_by_observation_id;
ALTER TABLE observations ADD COLUMN supersedes_observation_id TEXT REFERENCES observations(observation_id);
-- A correction is a NEW observation row with supersedes_observation_id
-- pointing BACKWARD to the observation it corrects, set once at INSERT
-- time. This is the opposite direction from migration 001's
-- superseded_by_observation_id (which pointed forward from the OLD row
-- to the NEW one, requiring the OLD row to be mutated after the fact -
-- incompatible with the immutability block above). Querying "what
-- corrected observation X" is now `SELECT * FROM observations WHERE
-- supersedes_observation_id = 'X'` instead of reading a field on X
-- itself.

CREATE TRIGGER trg_observations_no_update
BEFORE UPDATE ON observations
BEGIN
    SELECT RAISE(ABORT, 'observations is immutable: UPDATE is not permitted. Corrections are new rows with supersedes_observation_id set, never edits to existing rows.');
END;

CREATE TRIGGER trg_observations_no_delete
BEFORE DELETE ON observations
BEGIN
    SELECT RAISE(ABORT, 'observations is immutable: DELETE is not permitted.');
END;

-- ═══════════════════════════════════════════════════════════════════════
-- PART B: Typed identifier model - observation_identifiers.
--
-- Honesty note (per the instruction not to overclaim): this schema
-- cannot determine whether a caller INTENDS an ATN to be labeled ATN vs
-- APN - no database can validate human intent. What it does instead:
-- makes identifier_type an explicit, controlled (CHECK-constrained),
-- auditable (created_at, source_schema_field_or_null) column that can
-- never be silently rendered as a different type after the fact
-- (the whole table is immutable, below) - and separates raw from
-- normalized value storage so neither is conflated with the other or
-- with a different identifier type. The protection this provides is
-- structural and auditable, not a guarantee against a mislabeling
-- mistake made at data-entry time.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE observation_identifiers (
    identifier_id                      TEXT PRIMARY KEY,
    observation_id                     TEXT NOT NULL REFERENCES observations(observation_id),
    identifier_type                    TEXT NOT NULL CHECK (identifier_type IN (
                                        'ASSESSOR_APN', 'ATN', 'RECORDER_DOCUMENT_NUMBER',
                                        'TAX_ACCOUNT_NUMBER', 'AUCTION_ID', 'GIS_PARCEL_ID',
                                        'OTHER_SOURCE_IDENTIFIER'
                                        )),
    identifier_value_raw               TEXT NOT NULL,
    identifier_value_normalized_or_null TEXT,
    verification_status                TEXT NOT NULL CHECK (verification_status IN (
                                        'UNVERIFIED', 'SOURCE_ASSERTED', 'VERIFIED', 'CONFLICTED', 'UNKNOWN'
                                        )),
    source_schema_field_or_null        TEXT,
    created_at                         TEXT NOT NULL
);
CREATE INDEX idx_observation_identifiers_observation ON observation_identifiers(observation_id);
CREATE INDEX idx_observation_identifiers_type_value ON observation_identifiers(identifier_type, identifier_value_raw);
-- No UNIQUE constraint on (observation_id, identifier_type): one
-- observation may legitimately carry more than one identifier of the
-- same type in rare real-world cases (e.g. a source page listing both a
-- current and a prior recorder document number) - "an observation may
-- have multiple identifiers" is satisfied generally, not just across
-- distinct types.

CREATE TRIGGER trg_observation_identifiers_no_update
BEFORE UPDATE ON observation_identifiers
BEGIN
    SELECT RAISE(ABORT, 'observation_identifiers is immutable: UPDATE is not permitted.');
END;

CREATE TRIGGER trg_observation_identifiers_no_delete
BEFORE DELETE ON observation_identifiers
BEGIN
    SELECT RAISE(ABORT, 'observation_identifiers is immutable: DELETE is not permitted.');
END;

-- ═══════════════════════════════════════════════════════════════════════
-- PART C: Evidence disposition (quarantine) model.
--
-- Implemented as an append-only side table + a view for "current
-- disposition," rather than a mutable column on raw_evidence itself -
-- this is what lets Part A's immutability block on raw_evidence be
-- absolute (no "except for this one column" carve-out).
--
-- HONESTY NOTE on retroactivity (per the explicit instruction not to
-- overclaim): quarantining evidence AFTER a canonical_property_state has
-- already been marked VERIFIED using an observation backed by that
-- evidence does NOT retroactively change that canonical state's stored
-- verification_status. That status reflects what was true at the time
-- it was granted; it is not automatically revoked. What this migration
-- DOES guarantee: (1) no NEW observation can be created from evidence
-- that is quarantined at the time of the INSERT (Part C below), (2) no
-- NEW canonical_state_support link can be created from an observation
-- whose evidence is quarantined at the time of the INSERT (Part D
-- below), and (3) a view (v_canonical_state_currently_supported, Part D)
-- lets a caller check whether a given canonical state's support is
-- CURRENTLY still active-evidence-backed, separately from its stored
-- verification_status. Full historical invalidation (automatically
-- downgrading an already-VERIFIED row when its support is later
-- quarantined) is NOT implemented here and should not be assumed.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE evidence_disposition (
    disposition_id  TEXT PRIMARY KEY,
    evidence_id     TEXT NOT NULL REFERENCES raw_evidence(evidence_id),
    disposition     TEXT NOT NULL CHECK (disposition IN ('ACTIVE', 'QUARANTINED')),
    set_at          TEXT NOT NULL,
    reason          TEXT
);
CREATE INDEX idx_evidence_disposition_evidence ON evidence_disposition(evidence_id);
-- Append-only, same reasoning as observations: a disposition CHANGE is a
-- new row, never an edit to a prior one. This preserves a full history
-- of disposition changes (e.g. quarantined, then later reinstated, then
-- quarantined again) rather than only the current value.

CREATE TRIGGER trg_evidence_disposition_no_update
BEFORE UPDATE ON evidence_disposition
BEGIN
    SELECT RAISE(ABORT, 'evidence_disposition is append-only: UPDATE is not permitted.');
END;

CREATE TRIGGER trg_evidence_disposition_no_delete
BEFORE DELETE ON evidence_disposition
BEGIN
    SELECT RAISE(ABORT, 'evidence_disposition is append-only: DELETE is not permitted.');
END;

-- Current disposition = the most recently set_at row for that evidence_id,
-- or ACTIVE if no disposition row exists yet (evidence starts trusted by
-- default until explicitly quarantined).
CREATE VIEW v_evidence_current_disposition AS
SELECT
    e.evidence_id,
    COALESCE(
        (SELECT ed.disposition FROM evidence_disposition ed
         WHERE ed.evidence_id = e.evidence_id
         ORDER BY ed.set_at DESC, ed.disposition_id DESC
         LIMIT 1),
        'ACTIVE'
    ) AS current_disposition
FROM raw_evidence e;

-- Enforcement: quarantined evidence cannot support a NEW observation.
CREATE TRIGGER trg_observations_block_quarantined_evidence
BEFORE INSERT ON observations
WHEN (SELECT current_disposition FROM v_evidence_current_disposition WHERE evidence_id = NEW.evidence_id) = 'QUARANTINED'
BEGIN
    SELECT RAISE(ABORT, 'Cannot create an observation from evidence that is currently quarantined.');
END;

-- ═══════════════════════════════════════════════════════════════════════
-- PART D: Verified canonical-state rule.
--
-- Adds verification_status as a column DISTINCT from the existing
-- lifecycle_status (migration 001) - lifecycle_status describes where a
-- state is in the reconciliation workflow (draft/reconciled/stale/
-- contested/human_review_required); verification_status describes
-- whether it has been confirmed trustworthy enough to rely on
-- (UNVERIFIED/VERIFIED/HUMAN_CONFIRMED/CONFLICTED/UNKNOWN). The two are
-- independent: a RECONCILED state can still be UNVERIFIED.
--
-- Adds canonical_state_support as a normalized, immutable join table
-- between canonical_property_state and observations - replacing sole
-- reliance on the fields_json blob (migration 001) for provenance, per
-- the explicit instruction not to rely only on JSON for this
-- requirement. fields_json is left in place (still used for the actual
-- field VALUES), canonical_state_support is specifically for the
-- verification-support relationship.
-- ═══════════════════════════════════════════════════════════════════════

ALTER TABLE canonical_property_state ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED'
    CHECK (verification_status IN ('UNVERIFIED', 'VERIFIED', 'HUMAN_CONFIRMED', 'CONFLICTED', 'UNKNOWN'));

CREATE TABLE canonical_state_support (
    support_id                   TEXT PRIMARY KEY,
    canonical_property_state_id  TEXT NOT NULL REFERENCES canonical_property_state(state_id),
    observation_id                TEXT NOT NULL REFERENCES observations(observation_id),
    created_at                     TEXT NOT NULL
);
CREATE INDEX idx_canonical_state_support_state ON canonical_state_support(canonical_property_state_id);
CREATE INDEX idx_canonical_state_support_observation ON canonical_state_support(observation_id);

CREATE TRIGGER trg_canonical_state_support_no_update
BEFORE UPDATE ON canonical_state_support
BEGIN
    SELECT RAISE(ABORT, 'canonical_state_support is immutable: UPDATE is not permitted.');
END;

CREATE TRIGGER trg_canonical_state_support_no_delete
BEFORE DELETE ON canonical_state_support
BEGIN
    SELECT RAISE(ABORT, 'canonical_state_support is immutable: DELETE is not permitted.');
END;

-- Enforcement: a support link cannot be created from an observation whose
-- evidence is currently quarantined - this is the mechanism that
-- prevents a NEW canonical state from being (newly) supported by
-- quarantined-evidence-backed observations.
CREATE TRIGGER trg_canonical_state_support_block_quarantined
BEFORE INSERT ON canonical_state_support
WHEN (
    SELECT d.current_disposition
    FROM observations o
    JOIN v_evidence_current_disposition d ON d.evidence_id = o.evidence_id
    WHERE o.observation_id = NEW.observation_id
) = 'QUARANTINED'
BEGIN
    SELECT RAISE(ABORT, 'Cannot link a canonical_property_state to an observation whose evidence is currently quarantined.');
END;

-- Enforcement, part 1: a canonical_property_state row can NEVER be
-- INSERTed directly as VERIFIED/HUMAN_CONFIRMED. Ordering reason (per
-- the explicit instruction on how to handle this): canonical_state_support
-- rows reference canonical_property_state_id via a foreign key, so they
-- cannot be created before the state row they support exists - meaning
-- "at least one supporting observation" can never be true at the moment
-- of the state row's own INSERT. The workflow this forces: INSERT the
-- state as UNVERIFIED (or another non-verified value), INSERT its
-- canonical_state_support rows, THEN UPDATE verification_status - which
-- is when support can actually be checked (enforcement part 2, below).
CREATE TRIGGER trg_canonical_state_no_verified_on_insert
BEFORE INSERT ON canonical_property_state
WHEN NEW.verification_status IN ('VERIFIED', 'HUMAN_CONFIRMED')
BEGIN
    SELECT RAISE(ABORT, 'canonical_property_state cannot be created directly as VERIFIED or HUMAN_CONFIRMED. Insert as UNVERIFIED, add canonical_state_support rows, then UPDATE verification_status.');
END;

-- Enforcement, part 2: setting verification_status to VERIFIED/
-- HUMAN_CONFIRMED via UPDATE requires, at that moment: (a) at least one
-- canonical_state_support row for this state, (b) that support's
-- observation backed by evidence that is currently ACTIVE (not
-- quarantined), and (c) a parcel_matches row for this state's parcel_id
-- with status='confirmed' (migration 001's parcel_matches.status
-- vocabulary already covers both automatic and human-driven confirmation
-- - match_method='human_confirmed' is one way a match REACHES
-- status='confirmed', not a separate status value - see
-- migrations/README.md or this migration's own comments for that
-- mapping, since the requesting spec's wording ("confirmed or
-- human_confirmed parcel match") doesn't map 1:1 onto the existing
-- migration 001 vocabulary and this is the documented interpretation
-- used here).
CREATE TRIGGER trg_canonical_state_verify_requires_support
BEFORE UPDATE OF verification_status ON canonical_property_state
WHEN NEW.verification_status IN ('VERIFIED', 'HUMAN_CONFIRMED')
AND NOT EXISTS (
    SELECT 1
    FROM canonical_state_support css
    JOIN observations o ON o.observation_id = css.observation_id
    JOIN v_evidence_current_disposition d ON d.evidence_id = o.evidence_id
    WHERE css.canonical_property_state_id = NEW.state_id
      AND d.current_disposition = 'ACTIVE'
)
BEGIN
    SELECT RAISE(ABORT, 'Cannot set verification_status to VERIFIED/HUMAN_CONFIRMED: no canonical_state_support row backed by currently-ACTIVE evidence exists for this state.');
END;

CREATE TRIGGER trg_canonical_state_verify_requires_confirmed_match
BEFORE UPDATE OF verification_status ON canonical_property_state
WHEN NEW.verification_status IN ('VERIFIED', 'HUMAN_CONFIRMED')
AND NOT EXISTS (
    SELECT 1 FROM parcel_matches pm
    WHERE pm.parcel_id = NEW.parcel_id AND pm.status = 'confirmed'
)
BEGIN
    SELECT RAISE(ABORT, 'Cannot set verification_status to VERIFIED/HUMAN_CONFIRMED: no confirmed parcel_matches row exists for this state''s parcel_id.');
END;

-- Query-time honesty check (see the Part C note on retroactivity): does
-- this canonical state's support CURRENTLY still hold up, independent of
-- its stored verification_status? A state can be stored as VERIFIED
-- while this view reports FALSE, if its supporting evidence was
-- quarantined after verification - that divergence is intentional and
-- documented, not a bug.
CREATE VIEW v_canonical_state_currently_supported AS
SELECT
    cps.state_id,
    cps.parcel_id,
    cps.verification_status AS stored_verification_status,
    EXISTS (
        SELECT 1
        FROM canonical_state_support css
        JOIN observations o ON o.observation_id = css.observation_id
        JOIN v_evidence_current_disposition d ON d.evidence_id = o.evidence_id
        WHERE css.canonical_property_state_id = cps.state_id
          AND d.current_disposition = 'ACTIVE'
    ) AS has_active_support,
    EXISTS (
        SELECT 1 FROM parcel_matches pm
        WHERE pm.parcel_id = cps.parcel_id AND pm.status = 'confirmed'
    ) AS has_confirmed_match
FROM canonical_property_state cps;
