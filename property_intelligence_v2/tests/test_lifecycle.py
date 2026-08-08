"""
Tests for property_intelligence_v2/validation/lifecycle.py - proves the
transition validators accept legitimate transitions (including into
failure/terminal states, per rule 1: failure is a valid output) and
reject illegitimate ones.

Run: python3 property_intelligence_v2/tests/test_lifecycle.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validation"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "contracts"))

from lifecycle import (  # noqa: E402
    InvalidTransitionError,
    validate_canonical_state_transition,
    validate_exception_transition,
    validate_ingestion_run_transition,
    validate_parcel_match_transition,
)
from entities import (  # noqa: E402
    CanonicalStateLifecycle,
    ExceptionStatus,
    IngestionRunStatus,
    MatchStatus,
)


def test_ingestion_run_allows_attempted_to_failed_directly():
    """Failure is a valid output reachable without ever entering IN_PROGRESS
    (e.g. the connection itself fails before any work starts)."""
    validate_ingestion_run_transition(IngestionRunStatus.ATTEMPTED, IngestionRunStatus.FAILED)
    print("PASS: IngestionRun ATTEMPTED -> FAILED is a valid transition")


def test_ingestion_run_rejects_transition_out_of_terminal_state():
    try:
        validate_ingestion_run_transition(IngestionRunStatus.SUCCEEDED, IngestionRunStatus.FAILED)
        raise AssertionError("Expected InvalidTransitionError")
    except InvalidTransitionError:
        pass
    print("PASS: IngestionRun rejects any transition out of a terminal state (SUCCEEDED)")


def test_parcel_match_allows_confirmed_to_superseded():
    validate_parcel_match_transition(MatchStatus.CONFIRMED, MatchStatus.SUPERSEDED)
    print("PASS: ParcelMatch CONFIRMED -> SUPERSEDED is valid (a later, better match can supersede)")


def test_parcel_match_rejects_rejected_to_confirmed():
    try:
        validate_parcel_match_transition(MatchStatus.REJECTED, MatchStatus.CONFIRMED)
        raise AssertionError("Expected InvalidTransitionError")
    except InvalidTransitionError:
        pass
    print("PASS: ParcelMatch rejects REJECTED -> CONFIRMED (a rejected match is not revived; a new row is created instead)")


def test_canonical_state_allows_contested_as_a_real_outcome():
    validate_canonical_state_transition(CanonicalStateLifecycle.DRAFT, CanonicalStateLifecycle.CONTESTED)
    validate_canonical_state_transition(CanonicalStateLifecycle.CONTESTED, CanonicalStateLifecycle.HUMAN_REVIEW_REQUIRED)
    print("PASS: CanonicalPropertyState DRAFT -> CONTESTED -> HUMAN_REVIEW_REQUIRED is a valid path")


def test_canonical_state_rejects_transition_out_of_stale():
    try:
        validate_canonical_state_transition(CanonicalStateLifecycle.STALE, CanonicalStateLifecycle.RECONCILED)
        raise AssertionError("Expected InvalidTransitionError")
    except InvalidTransitionError:
        pass
    print("PASS: CanonicalPropertyState rejects any transition out of STALE (a new version row supersedes it instead)")


def test_exception_allows_open_to_resolved_directly():
    """A genuinely trivial exception can resolve immediately without a retry/fallback/quarantine step."""
    validate_exception_transition(ExceptionStatus.OPEN, ExceptionStatus.RESOLVED)
    print("PASS: Exception OPEN -> RESOLVED directly is valid")


def test_exception_rejects_resolved_to_open():
    try:
        validate_exception_transition(ExceptionStatus.RESOLVED, ExceptionStatus.OPEN)
        raise AssertionError("Expected InvalidTransitionError")
    except InvalidTransitionError:
        pass
    print("PASS: Exception rejects RESOLVED -> OPEN (resolved is terminal; a recurrence is a new exception row)")


def test_exception_full_retry_then_escalate_path():
    validate_exception_transition(ExceptionStatus.OPEN, ExceptionStatus.RETRIED)
    validate_exception_transition(ExceptionStatus.RETRIED, ExceptionStatus.ESCALATED)
    validate_exception_transition(ExceptionStatus.ESCALATED, ExceptionStatus.RESOLVED)
    print("PASS: Exception OPEN -> RETRIED -> ESCALATED -> RESOLVED is a valid full path")


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
