"""
Phase 1 data contracts for property_intelligence_v2.

Architecture:

    Parcel Master
      -> Immutable Source Observations
        -> Reconciliation
          -> Canonical Property State
            -> Reconciliation Feedback
              -> (future) Derived Intelligence

Nine entities, in the order data actually flows through them:

    source_registry          - what sources exist, per county
    ingestion_runs            - one row per attempt to pull from a source
    raw_evidence               - the immutable artifact an ingestion run captured
    observations                - immutable, atomic facts extracted from raw_evidence
    parcels                      - the master identity registry (bare identity only)
    parcel_matches                 - links observations to parcels, with method/confidence
    canonical_property_state        - the current, reconciled, versioned best-known state
    reconciliation_feedback           - the audit trail of how that state was reconciled
    exceptions                          - anomalies at any stage, with a chosen next action

Design rules this file follows throughout (do not violate them when adding
fields later):

  1. A failure is a valid, first-class output - not something to swallow,
     retry silently, or represent as an absent record. Every stage that
     can fail has an explicit status covering failure, and a `exceptions`
     row is the mechanism for classifying what happened and choosing what
     to do next (retry / fallback / quarantine / human_review), not a
     stack trace or a silently-empty result.

  2. raw_evidence and observations are IMMUTABLE. Never edit one in
     place - a correction is a NEW observation that supersedes an old
     one, with the supersession itself recorded (not a silent overwrite).
     This is the direct lesson from this session's real incidents: the
     Nevada stale-cycle mislabel, the Kern ATN/APN conflation, and the
     Del Norte owner-name correction (HOUTS DORA DAVIS -> COLOTI RENE) -
     all three were correctly handled in the legacy pipeline by keeping
     the old and new facts both visible with a stated reason, never by
     quietly replacing one string with another.

  3. Identity is never overloaded. A parcel's bare identity
     (`parcels.parcel_id`) is deliberately NOT derived from any single
     county's own identifier scheme (APN, ATN, or otherwise) - that
     conflation is exactly what caused the Kern ATN-labeled-as-APN defect
     in the legacy pipeline. County-specific identifiers live in
     `observations` (as raw, typed facts) and get connected to a parcel
     only through an explicit, auditable `parcel_matches` row - never
     baked into parcel_id itself.

  4. Nothing here is a scraper, adapter, monitor, dossier, dashboard,
     export, scoring model, or ranking. This module defines shapes only.

  5. Do not populate this module, or anything that imports it, with real
     or synthetic California county data. It has none, and should have
     none until an explicit, separately-authorized migration step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ── Shared enums ─────────────────────────────────────────────────────────

class ConfidenceLevel(str, Enum):
    """
    How an observation's value was established. Mirrors the same concept
    already proven in the legacy property_model.py (built during the
    2026-08-08 remediation session) - kept as a separate definition here
    rather than imported, since v2 is intentionally decoupled from legacy
    code per the isolation rule (see property_intelligence_v2/README.md).
    """
    CONFIRMED = "confirmed"                # directly read from a live official source this run
    CARRIED_FORWARD = "carried_forward"    # seen on a prior run, not re-verified this run
    SOURCE_LIST_ONLY = "source_list_only"  # present on a source list, never independently verified
    UNCONFIRMED = "unconfirmed"            # present but contradicted, or not yet checked


class NextAction(str, Enum):
    """
    The "choose next action" step of the failure lifecycle:
    attempt -> observe -> classify -> save evidence -> record outcome ->
    choose next action -> retry / fallback / quarantine / human_review.
    Used by both IngestionRun and Exception - the same vocabulary applies
    whether the failure surfaced during an ingestion attempt or was
    classified afterward as an exception.
    """
    RETRY = "retry"
    FALLBACK = "fallback"
    QUARANTINE = "quarantine"
    HUMAN_REVIEW = "human_review"
    NONE = "none"  # succeeded outright, or already terminally resolved


class SourceType(str, Enum):
    ASSESSOR = "assessor"
    RECORDER = "recorder"
    TAX_COLLECTOR = "tax_collector"
    AUCTION_PLATFORM = "auction_platform"
    GIS = "gis"
    OTHER = "other"


class SourceAccessLevel(str, Enum):
    """
    Reuses the recorder-capability taxonomy already established this
    session for the legacy pipeline's county dispatch work
    (RECORDER_FULL / RECORDER_INDEX_ONLY / RECORDER_MANUAL_ONLY /
    RECORDER_BLOCKED / RECORDER_UNKNOWN), generalized beyond recorders to
    any source type, since the same distinctions (full access vs.
    index-only vs. manual-only vs. blocked vs. untested) apply to
    assessor, tax-collector, and auction-platform sources too.
    """
    FULL = "full"
    INDEX_ONLY = "index_only"
    MANUAL_ONLY = "manual_only"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class IngestionRunStatus(str, Enum):
    ATTEMPTED = "attempted"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class ParcelStatus(str, Enum):
    ACTIVE = "active"
    MERGED = "merged"    # this parcel_id was merged into another (lot consolidation)
    SPLIT = "split"       # this parcel_id was split into others (lot split)
    RETIRED = "retired"  # no longer a valid parcel identity for any other reason


class MatchMethod(str, Enum):
    EXACT_IDENTIFIER = "exact_identifier"
    FUZZY = "fuzzy"
    HUMAN_CONFIRMED = "human_confirmed"
    UNMATCHED = "unmatched"  # observation exists but has not been linked to any parcel yet


class MatchStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"  # a later match replaced this one - kept, not deleted


class CanonicalStateLifecycle(str, Enum):
    DRAFT = "draft"                              # reconciliation in progress, not yet final
    RECONCILED = "reconciled"                     # reconciliation completed cleanly
    STALE = "stale"                               # superseded by a newer version for this parcel
    CONTESTED = "contested"                       # unresolved conflict between observations
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class ReconciliationResolutionMethod(str, Enum):
    MOST_RECENT = "most_recent"
    HIGHEST_CONFIDENCE = "highest_confidence"
    HUMAN_DECIDED = "human_decided"
    UNRESOLVED = "unresolved"  # a real, valid outcome - not every conflict resolves automatically


class ExceptionStage(str, Enum):
    INGESTION = "ingestion"
    OBSERVATION = "observation"
    MATCHING = "matching"
    RECONCILIATION = "reconciliation"
    OTHER = "other"


class ExceptionClassification(str, Enum):
    """The "classify" step - what kind of thing went wrong."""
    TRANSIENT_ERROR = "transient_error"
    SOURCE_UNAVAILABLE = "source_unavailable"
    DATA_CONTRADICTION = "data_contradiction"
    SCHEMA_MISMATCH = "schema_mismatch"
    RATE_LIMITED = "rate_limited"
    ACCESS_BLOCKED = "access_blocked"
    UNKNOWN = "unknown"


class ExceptionSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExceptionStatus(str, Enum):
    OPEN = "open"
    RETRIED = "retried"
    FALLBACK_APPLIED = "fallback_applied"
    QUARANTINED = "quarantined"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


# ── Entities, in pipeline order ──────────────────────────────────────────

@dataclass
class SourceRegistryEntry:
    """A known, named source of county data. One row per (county, source_type, name) -
    a county can have more than one source of the same type (e.g. two different
    recorder-search modes)."""
    source_id: str
    county: str
    county_fips: str
    source_type: SourceType
    name: str
    base_url: str | None
    access_level: SourceAccessLevel
    registered_at: datetime
    last_verified_at: datetime | None = None
    reliability_notes: str | None = None


@dataclass
class IngestionRun:
    """One attempt to pull data from a source. Always created at the start
    of an attempt, before it's known whether the attempt will succeed -
    per rule 1, a failed run is a completed, valid IngestionRun row, not
    a missing one."""
    run_id: str
    source_id: str
    started_at: datetime
    status: IngestionRunStatus
    finished_at: datetime | None = None
    attempted_count: int | None = None
    succeeded_count: int | None = None
    failed_count: int | None = None
    next_action: NextAction = NextAction.NONE
    notes: str | None = None


@dataclass
class RawEvidence:
    """An immutable captured artifact (a specific HTTP response, PDF,
    HTML page, JSON payload, etc.) produced by one IngestionRun. Never
    edited after creation - content_hash exists specifically so any
    later code can verify a stored artifact hasn't drifted from what was
    actually captured."""
    evidence_id: str
    ingestion_run_id: str
    source_id: str
    retrieved_at: datetime
    content_hash: str  # sha256 of the raw captured bytes
    content_type: str  # e.g. "application/pdf", "text/html", "application/json"
    source_url_or_identifier: str
    storage_path: str | None = None  # where the raw bytes live - storage backend is not prescribed here
    immutable: bool = True


@dataclass
class Observation:
    """One atomic, immutable fact extracted from a RawEvidence record.
    "Atomic" means one (field_name, field_value) pair per row, not a
    whole parsed record bundled together - this is what makes
    reconciliation and supersession possible at the field level rather
    than only at the whole-record level."""
    observation_id: str
    evidence_id: str
    observed_at: datetime
    county: str
    source_identifier_type: str  # e.g. "atn", "apn", "recorder_document_number" - free text, not
                                  # a closed enum, since different counties surface different
                                  # identifier types and this contract must not assume it knows
                                  # all of them in advance
    source_identifier_value: str
    field_name: str   # what fact this is about, e.g. "assessed_value", "owner_name", "lien_status"
    field_value: str  # always stored as the raw observed string - typed interpretation is a
                       # concern for a later layer, not for this immutable record
    confidence: ConfidenceLevel
    superseded_by_observation_id: str | None = None  # rule 2: corrections are new rows, linked, never edits
    immutable: bool = True


@dataclass
class Parcel:
    """The master identity registry. Deliberately minimal - per rule 3,
    no county-specific identifier is stored here. A Parcel is just an
    assertion that "this durable identity exists"; everything else about
    it comes from observations, linked via ParcelMatch."""
    parcel_id: str
    county: str
    county_fips: str
    created_at: datetime
    status: ParcelStatus = ParcelStatus.ACTIVE
    merged_into_parcel_id: str | None = None  # set only when status == MERGED
    notes: str | None = None


@dataclass
class ParcelMatch:
    """Links one Observation to one Parcel. An Observation may exist with
    no ParcelMatch at all (status effectively "unmatched") - this is a
    valid, expected state while entity resolution catches up, not an
    error."""
    match_id: str
    observation_id: str
    parcel_id: str | None  # None while unmatched
    match_method: MatchMethod
    match_confidence: float  # 0.0-1.0
    status: MatchStatus
    matched_at: datetime | None = None
    matched_by: str | None = None  # system identifier or human reviewer id


@dataclass
class CanonicalFieldValue:
    """One field's current reconciled value inside a CanonicalPropertyState -
    always traceable back to the specific observations that produced it,
    never a bare value with no provenance."""
    value: str
    confidence: ConfidenceLevel
    source_observation_ids: list[str]
    last_reconciled_at: datetime


@dataclass
class CanonicalPropertyState:
    """The current, versioned, reconciled best-known state of a parcel.
    Mutable in the sense that a NEW version is created as reconciliation
    runs again - but a specific (parcel_id, version) row, once created,
    is not edited; superseded_by_state_id points forward instead."""
    state_id: str
    parcel_id: str
    version: int
    as_of: datetime
    fields: dict[str, CanonicalFieldValue] = field(default_factory=dict)
    lifecycle_status: CanonicalStateLifecycle = CanonicalStateLifecycle.DRAFT
    superseded_by_state_id: str | None = None


@dataclass
class ReconciliationFeedback:
    """The audit trail of one reconciliation event: which observations
    were considered, what conflicts were found between them, and how (or
    whether) each was resolved. This is what "feeds back" into the
    system - a record of reconciliation's own behavior, not just its
    output."""
    feedback_id: str
    canonical_property_state_id: str
    observation_ids_considered: list[str]
    resolved_at: datetime
    resolution_method: ReconciliationResolutionMethod
    conflicts_detected: list[dict] = field(default_factory=list)  # each: {field_name, conflicting_values, resolution}
    notes: str | None = None


@dataclass
class Exception_:  # trailing underscore: "Exception" shadows the Python builtin
    """An anomaly at any stage of the pipeline, with an explicit
    classification and a chosen next action - the formal implementation
    of rule 1 (failure is a valid output). Generalizes the
    county-signal-exception-log.csv / county_exception_ledger.csv pattern
    already proven in the legacy pipeline this session, decoupled from
    county-specific fields."""
    exception_id: str
    occurred_at: datetime
    stage: ExceptionStage
    related_entity_type: str  # e.g. "ingestion_run", "observation", "parcel_match", "canonical_property_state"
    related_entity_id: str
    classification: ExceptionClassification
    severity: ExceptionSeverity
    next_action: NextAction
    status: ExceptionStatus
    evidence_id: str | None = None
    notes: str | None = None
