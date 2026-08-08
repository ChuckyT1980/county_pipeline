"""
Tests for property_intelligence_v2/contracts/entities.py.

No real or synthetic California county data anywhere in this file -
every value used is a structural placeholder ("TEST-*", generic dates,
made-up counties are avoided in favor of clearly-fake identifiers) chosen
only to exercise the shape of each contract, matching the instruction not
to populate parcels/observations with real or synthetic CA data.

Matches the legacy repository's existing test convention (see
tests/test_lead_status.py at the repo root): plain assertions, no pytest
dependency, exits non-zero on failure.

Run: python3 property_intelligence_v2/tests/test_contracts.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "contracts"))

from entities import (
    CanonicalFieldValue,
    CanonicalPropertyState,
    CanonicalStateLifecycle,
    ConfidenceLevel,
    Exception_,
    ExceptionClassification,
    ExceptionSeverity,
    ExceptionStage,
    ExceptionStatus,
    IngestionRun,
    IngestionRunStatus,
    MatchMethod,
    MatchStatus,
    NextAction,
    Observation,
    Parcel,
    ParcelMatch,
    ParcelStatus,
    RawEvidence,
    ReconciliationFeedback,
    ReconciliationResolutionMethod,
    SourceAccessLevel,
    SourceRegistryEntry,
    SourceType,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_source_registry_entry_constructs():
    s = SourceRegistryEntry(
        source_id="SRC-TEST-1", county="TESTCOUNTY", county_fips="000",
        source_type=SourceType.ASSESSOR, name="Test Assessor Search",
        base_url="https://example.invalid/assessor", access_level=SourceAccessLevel.FULL,
        registered_at=NOW,
    )
    assert s.source_type == SourceType.ASSESSOR
    assert s.last_verified_at is None
    print("PASS: SourceRegistryEntry constructs with required + defaulted optional fields")


def test_ingestion_run_failure_is_a_valid_terminal_state():
    """Rule 1: a failed run is just as valid a row as a succeeded one."""
    r = IngestionRun(
        run_id="RUN-TEST-1", source_id="SRC-TEST-1", started_at=NOW,
        status=IngestionRunStatus.FAILED, next_action=NextAction.RETRY,
        notes="test fixture: simulated network timeout",
    )
    assert r.status == IngestionRunStatus.FAILED
    assert r.next_action == NextAction.RETRY
    print("PASS: IngestionRun with status=FAILED constructs cleanly (failure is a valid output)")


def test_raw_evidence_is_immutable_by_default():
    e = RawEvidence(
        evidence_id="EV-TEST-1", ingestion_run_id="RUN-TEST-1", source_id="SRC-TEST-1",
        retrieved_at=NOW, content_hash="0" * 64, content_type="text/html",
        source_url_or_identifier="https://example.invalid/page",
    )
    assert e.immutable is True
    print("PASS: RawEvidence defaults to immutable=True")


def test_observation_is_atomic_and_supersedable():
    o1 = Observation(
        observation_id="OBS-TEST-1", evidence_id="EV-TEST-1", observed_at=NOW,
        county="TESTCOUNTY", source_identifier_type="test_identifier",
        source_identifier_value="TEST-000-000-000", field_name="owner_name",
        field_value="TEST OWNER OLD", confidence=ConfidenceLevel.SOURCE_LIST_ONLY,
    )
    o2 = Observation(
        observation_id="OBS-TEST-2", evidence_id="EV-TEST-2", observed_at=NOW,
        county="TESTCOUNTY", source_identifier_type="test_identifier",
        source_identifier_value="TEST-000-000-000", field_name="owner_name",
        field_value="TEST OWNER NEW", confidence=ConfidenceLevel.CONFIRMED,
    )
    assert o1.superseded_by_observation_id is None
    o1.superseded_by_observation_id = o2.observation_id  # the correction pattern: link forward, never delete o1
    assert o1.superseded_by_observation_id == "OBS-TEST-2"
    assert o1.field_value == "TEST OWNER OLD", "o1's own recorded value must never change, even when superseded"
    print("PASS: Observation supersession links forward without mutating the original's field_value")


def test_parcel_master_never_carries_a_county_specific_identifier():
    """Rule 3: parcel identity is deliberately bare - this test exists
    specifically to catch a future regression that adds an apn/atn field
    directly onto Parcel, which is exactly the conflation that caused the
    legacy Kern ATN/APN defect."""
    p = Parcel(parcel_id="PARCEL-TEST-1", county="TESTCOUNTY", county_fips="000", created_at=NOW)
    field_names = {f for f in p.__dataclass_fields__}
    forbidden = {"apn", "atn", "assessor_apn", "source_identifier", "source_identifier_value"}
    assert not (field_names & forbidden), f"Parcel must not carry a county-specific identifier field, found: {field_names & forbidden}"
    print("PASS: Parcel carries no county-specific identifier field (identity stays bare per rule 3)")


def test_parcel_match_allows_unmatched_state():
    m = ParcelMatch(
        match_id="MATCH-TEST-1", observation_id="OBS-TEST-1", parcel_id=None,
        match_method=MatchMethod.UNMATCHED, match_confidence=0.0, status=MatchStatus.PENDING,
    )
    assert m.parcel_id is None
    print("PASS: ParcelMatch allows parcel_id=None (unmatched is a valid state, not an error)")


def test_canonical_property_state_fields_carry_provenance():
    cfv = CanonicalFieldValue(
        value="TEST OWNER NEW", confidence=ConfidenceLevel.CONFIRMED,
        source_observation_ids=["OBS-TEST-2"], last_reconciled_at=NOW,
    )
    state = CanonicalPropertyState(
        state_id="STATE-TEST-1", parcel_id="PARCEL-TEST-1", version=1, as_of=NOW,
        fields={"owner_name": cfv}, lifecycle_status=CanonicalStateLifecycle.RECONCILED,
    )
    assert state.fields["owner_name"].source_observation_ids == ["OBS-TEST-2"]
    print("PASS: CanonicalPropertyState field values carry source_observation_ids provenance")


def test_reconciliation_feedback_records_unresolved_conflicts_honestly():
    """Rule 1 applies here too: UNRESOLVED is a legitimate resolution_method value."""
    fb = ReconciliationFeedback(
        feedback_id="FB-TEST-1", canonical_property_state_id="STATE-TEST-1",
        observation_ids_considered=["OBS-TEST-1", "OBS-TEST-2"], resolved_at=NOW,
        resolution_method=ReconciliationResolutionMethod.UNRESOLVED,
        conflicts_detected=[{"field_name": "owner_name", "conflicting_values": ["TEST OWNER OLD", "TEST OWNER NEW"], "resolution": None}],
    )
    assert fb.resolution_method == ReconciliationResolutionMethod.UNRESOLVED
    assert len(fb.conflicts_detected) == 1
    print("PASS: ReconciliationFeedback allows resolution_method=UNRESOLVED as a first-class outcome")


def test_exception_requires_classification_and_next_action():
    exc = Exception_(
        exception_id="EXC-TEST-1", occurred_at=NOW, stage=ExceptionStage.INGESTION,
        related_entity_type="ingestion_run", related_entity_id="RUN-TEST-1",
        classification=ExceptionClassification.SOURCE_UNAVAILABLE,
        severity=ExceptionSeverity.HIGH, next_action=NextAction.RETRY, status=ExceptionStatus.OPEN,
    )
    assert exc.classification == ExceptionClassification.SOURCE_UNAVAILABLE
    assert exc.next_action == NextAction.RETRY
    print("PASS: Exception_ constructs with required classification + next_action fields")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
