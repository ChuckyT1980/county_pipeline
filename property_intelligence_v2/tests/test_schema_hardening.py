"""
Tests for property_intelligence_v2/migrations/002_integrity_hardening.sql.

Applies migration 001 followed by migration 002 (via apply_schema, the
same single code path production code would use) to a fresh temporary
in-memory SQLite database for every test. Never touches a file on disk.
All fixture values use an explicit TEST_ONLY_ prefix.

This file exists specifically to prove the six gaps identified in the
read-only audit of commit d741447 are now backed by real SQL enforcement
- not to re-prove what tests/test_schema.py already covers for migration
001 alone.

Pinned to target_version=2 (same reasoning as test_schema.py's pin to
target_version=1): migration 003 adds a UNIQUE index this file's fixtures
don't need to exercise, and pinning keeps this file testing 001+002 in
isolation regardless of what later migrations add. tests/
test_evidence_identity_migration.py is what tests 003 specifically.

Run: python3 property_intelligence_v2/tests/test_schema_hardening.py
"""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "migrations"))

from apply_schema import apply_schema, get_applied_version  # noqa: E402

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn, target_version=2)  # 001 then 002 only, in order, via the one shared code path
    return conn


def _seed_minimal_chain(conn: sqlite3.Connection) -> None:
    """source_registry -> ingestion_runs -> raw_evidence -> parcels, no observation yet."""
    conn.execute(
        "INSERT INTO source_registry (source_id, county, county_fips, source_type, name, base_url, access_level, registered_at) VALUES (?,?,?,?,?,?,?,?)",
        ("TEST_ONLY_SRC_1", "TEST_ONLY_COUNTY", "000", "assessor", "TEST_ONLY Source", "https://example.invalid", "full", NOW),
    )
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        ("TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW, "succeeded"),
    )
    conn.execute(
        "INSERT INTO raw_evidence (evidence_id, ingestion_run_id, source_id, retrieved_at, content_hash, content_type, source_url_or_identifier) VALUES (?,?,?,?,?,?,?)",
        ("TEST_ONLY_EV_1", "TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW, "0" * 64, "text/html", "https://example.invalid/page"),
    )
    conn.execute(
        "INSERT INTO parcels (parcel_id, county, county_fips, created_at) VALUES (?,?,?,?)",
        ("TEST_ONLY_PARCEL_1", "TEST_ONLY_COUNTY", "000", NOW),
    )
    conn.commit()


def _seed_one_observation(conn: sqlite3.Connection, observation_id: str = "TEST_ONLY_OBS_1", evidence_id: str = "TEST_ONLY_EV_1") -> None:
    conn.execute(
        "INSERT INTO observations (observation_id, evidence_id, observed_at, county, field_name, field_value, confidence) VALUES (?,?,?,?,?,?,?)",
        (observation_id, evidence_id, NOW, "TEST_ONLY_COUNTY", "owner_name", "TEST_ONLY OWNER", "confirmed"),
    )
    conn.commit()


# ── Migration application itself ─────────────────────────────────────────

def test_migrations_001_and_002_apply_in_order():
    conn = _fresh_conn()
    assert get_applied_version(conn) == 2
    versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]
    assert versions == [1, 2], f"expected migrations applied in order [1, 2], got {versions}"
    print("PASS: migration 001 then 002 applied in order via the single apply_schema() path (pinned to target_version=2)")


# ── 1. Evidence and observation immutability ─────────────────────────────

def test_update_raw_evidence_fails():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    try:
        conn.execute("UPDATE raw_evidence SET content_hash = 'x' WHERE evidence_id = 'TEST_ONLY_EV_1'")
        raise AssertionError("Expected sqlite3.IntegrityError")
    except sqlite3.IntegrityError:
        pass
    print("PASS: UPDATE raw_evidence fails")


def test_delete_raw_evidence_fails():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    try:
        conn.execute("DELETE FROM raw_evidence WHERE evidence_id = 'TEST_ONLY_EV_1'")
        raise AssertionError("Expected sqlite3.IntegrityError")
    except sqlite3.IntegrityError:
        pass
    print("PASS: DELETE raw_evidence fails")


def test_update_observations_fails():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn)
    try:
        conn.execute("UPDATE observations SET field_value = 'CHANGED' WHERE observation_id = 'TEST_ONLY_OBS_1'")
        raise AssertionError("Expected sqlite3.IntegrityError")
    except sqlite3.IntegrityError:
        pass
    print("PASS: UPDATE observations fails")


def test_delete_observations_fails():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn)
    try:
        conn.execute("DELETE FROM observations WHERE observation_id = 'TEST_ONLY_OBS_1'")
        raise AssertionError("Expected sqlite3.IntegrityError")
    except sqlite3.IntegrityError:
        pass
    print("PASS: DELETE observations fails")


def test_correction_is_new_observation_with_supersedes_link():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn, "TEST_ONLY_OBS_1")
    # The correction: a NEW row, pointing backward - the old row is never touched.
    conn.execute(
        "INSERT INTO observations (observation_id, evidence_id, observed_at, county, field_name, field_value, confidence, supersedes_observation_id) VALUES (?,?,?,?,?,?,?,?)",
        ("TEST_ONLY_OBS_2", "TEST_ONLY_EV_1", NOW, "TEST_ONLY_COUNTY", "owner_name", "TEST_ONLY OWNER CORRECTED", "confirmed", "TEST_ONLY_OBS_1"),
    )
    old_value = conn.execute("SELECT field_value FROM observations WHERE observation_id = 'TEST_ONLY_OBS_1'").fetchone()[0]
    new_row = conn.execute("SELECT field_value, supersedes_observation_id FROM observations WHERE observation_id = 'TEST_ONLY_OBS_2'").fetchone()
    assert old_value == "TEST_ONLY OWNER", "the original observation's own field_value must be untouched"
    assert new_row == ("TEST_ONLY OWNER CORRECTED", "TEST_ONLY_OBS_1")
    print("PASS: a correction is a new observation row with supersedes_observation_id, old row untouched")


# ── 2. Typed identifier model ─────────────────────────────────────────────

def test_observation_can_hold_atn_and_recorder_doc_number_distinctly():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn)
    conn.execute(
        "INSERT INTO observation_identifiers (identifier_id, observation_id, identifier_type, identifier_value_raw, verification_status, created_at) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_ID_ATN", "TEST_ONLY_OBS_1", "ATN", "017-490-06-00-3", "SOURCE_ASSERTED", NOW),
    )
    conn.execute(
        "INSERT INTO observation_identifiers (identifier_id, observation_id, identifier_type, identifier_value_raw, verification_status, created_at) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_ID_DOC", "TEST_ONLY_OBS_1", "RECORDER_DOCUMENT_NUMBER", "226037165", "VERIFIED", NOW),
    )
    types = {r[0] for r in conn.execute("SELECT identifier_type FROM observation_identifiers WHERE observation_id = 'TEST_ONLY_OBS_1'").fetchall()}
    assert types == {"ATN", "RECORDER_DOCUMENT_NUMBER"}
    assert "ASSESSOR_APN" not in types, "neither the ATN nor the recorder document number is stored as an APN"
    print("PASS: one observation holds both an ATN and a recorder document number, neither typed as APN")


def test_raw_and_normalized_apn_stored_separately():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn)
    conn.execute(
        "INSERT INTO observation_identifiers (identifier_id, observation_id, identifier_type, identifier_value_raw, identifier_value_normalized_or_null, verification_status, created_at) VALUES (?,?,?,?,?,?,?)",
        ("TEST_ONLY_ID_APN", "TEST_ONLY_OBS_1", "ASSESSOR_APN", "017-490-06", "01749006", "UNVERIFIED", NOW),
    )
    row = conn.execute(
        "SELECT identifier_value_raw, identifier_value_normalized_or_null FROM observation_identifiers WHERE identifier_id = 'TEST_ONLY_ID_APN'"
    ).fetchone()
    assert row == ("017-490-06", "01749006")
    print("PASS: raw APN ('017-490-06') and normalized APN ('01749006') stored in separate columns on one row")


def test_identifier_type_vocabulary_is_enforced():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn)
    try:
        conn.execute(
            "INSERT INTO observation_identifiers (identifier_id, observation_id, identifier_type, identifier_value_raw, verification_status, created_at) VALUES (?,?,?,?,?,?)",
            ("TEST_ONLY_ID_BAD", "TEST_ONLY_OBS_1", "NOT_A_REAL_TYPE", "X", "UNVERIFIED", NOW),
        )
        raise AssertionError("Expected sqlite3.IntegrityError for an out-of-vocabulary identifier_type")
    except sqlite3.IntegrityError:
        pass
    print("PASS: an out-of-vocabulary identifier_type is rejected by the CHECK constraint")


def test_observation_identifiers_is_immutable():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn)
    conn.execute(
        "INSERT INTO observation_identifiers (identifier_id, observation_id, identifier_type, identifier_value_raw, verification_status, created_at) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_ID_1", "TEST_ONLY_OBS_1", "ATN", "017-490-06-00-3", "SOURCE_ASSERTED", NOW),
    )
    try:
        conn.execute("UPDATE observation_identifiers SET identifier_value_raw = 'X' WHERE identifier_id = 'TEST_ONLY_ID_1'")
        raise AssertionError("Expected sqlite3.IntegrityError")
    except sqlite3.IntegrityError:
        pass
    print("PASS: observation_identifiers is immutable (UPDATE rejected)")


# ── 3. Quarantine model ────────────────────────────────────────────────────

def test_quarantined_evidence_blocks_new_observation():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    conn.execute(
        "INSERT INTO evidence_disposition (disposition_id, evidence_id, disposition, set_at, reason) VALUES (?,?,?,?,?)",
        ("TEST_ONLY_DISP_1", "TEST_ONLY_EV_1", "QUARANTINED", NOW, "TEST_ONLY quarantine reason"),
    )
    try:
        _seed_one_observation(conn)
        raise AssertionError("Expected sqlite3.IntegrityError - evidence is quarantined")
    except sqlite3.IntegrityError:
        pass
    print("PASS: quarantined evidence cannot support a new observation")


def test_evidence_disposition_defaults_to_active_and_is_append_only():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    current = conn.execute(
        "SELECT current_disposition FROM v_evidence_current_disposition WHERE evidence_id = 'TEST_ONLY_EV_1'"
    ).fetchone()[0]
    assert current == "ACTIVE", "evidence with no disposition row yet must default to ACTIVE"
    conn.execute(
        "INSERT INTO evidence_disposition (disposition_id, evidence_id, disposition, set_at, reason) VALUES (?,?,?,?,?)",
        ("TEST_ONLY_DISP_1", "TEST_ONLY_EV_1", "QUARANTINED", NOW, "TEST_ONLY reason"),
    )
    try:
        conn.execute("UPDATE evidence_disposition SET disposition = 'ACTIVE' WHERE disposition_id = 'TEST_ONLY_DISP_1'")
        raise AssertionError("Expected sqlite3.IntegrityError - evidence_disposition is append-only")
    except sqlite3.IntegrityError:
        pass
    print("PASS: evidence defaults to ACTIVE with no disposition row; evidence_disposition itself is append-only")


# ── 4. Verified canonical-state rule ───────────────────────────────────────

def test_verified_canonical_state_cannot_be_created_directly():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    try:
        conn.execute(
            "INSERT INTO canonical_property_state (state_id, parcel_id, version, as_of, fields_json, lifecycle_status, verification_status) VALUES (?,?,?,?,?,?,?)",
            ("TEST_ONLY_STATE_BAD", "TEST_ONLY_PARCEL_1", 1, NOW, "{}", "draft", "VERIFIED"),
        )
        raise AssertionError("Expected sqlite3.IntegrityError")
    except sqlite3.IntegrityError:
        pass
    print("PASS: a canonical_property_state row cannot be INSERTed directly as VERIFIED")


def test_verified_update_fails_without_support_or_confirmed_match():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    conn.execute(
        "INSERT INTO canonical_property_state (state_id, parcel_id, version, as_of, fields_json, lifecycle_status) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_STATE_1", "TEST_ONLY_PARCEL_1", 1, NOW, "{}", "draft"),
    )
    # No support, no match yet - must fail.
    try:
        conn.execute("UPDATE canonical_property_state SET verification_status = 'VERIFIED' WHERE state_id = 'TEST_ONLY_STATE_1'")
        raise AssertionError("Expected sqlite3.IntegrityError - no support and no confirmed match exist yet")
    except sqlite3.IntegrityError:
        pass

    # Add support only - still must fail (no confirmed parcel match yet).
    _seed_one_observation(conn)
    conn.execute(
        "INSERT INTO canonical_state_support (support_id, canonical_property_state_id, observation_id, created_at) VALUES (?,?,?,?)",
        ("TEST_ONLY_SUP_1", "TEST_ONLY_STATE_1", "TEST_ONLY_OBS_1", NOW),
    )
    try:
        conn.execute("UPDATE canonical_property_state SET verification_status = 'VERIFIED' WHERE state_id = 'TEST_ONLY_STATE_1'")
        raise AssertionError("Expected sqlite3.IntegrityError - support exists but no confirmed parcel_match yet")
    except sqlite3.IntegrityError:
        pass
    print("PASS: VERIFIED update fails with neither support nor a confirmed match, and fails with only support and no confirmed match")


def test_verified_update_succeeds_with_support_and_confirmed_match():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn)
    conn.execute(
        "INSERT INTO canonical_property_state (state_id, parcel_id, version, as_of, fields_json, lifecycle_status) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_STATE_1", "TEST_ONLY_PARCEL_1", 1, NOW, "{}", "draft"),
    )
    conn.execute(
        "INSERT INTO canonical_state_support (support_id, canonical_property_state_id, observation_id, created_at) VALUES (?,?,?,?)",
        ("TEST_ONLY_SUP_1", "TEST_ONLY_STATE_1", "TEST_ONLY_OBS_1", NOW),
    )
    conn.execute(
        "INSERT INTO parcel_matches (match_id, observation_id, parcel_id, match_method, match_confidence, status) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_MATCH_1", "TEST_ONLY_OBS_1", "TEST_ONLY_PARCEL_1", "exact_identifier", 1.0, "confirmed"),
    )
    conn.execute("UPDATE canonical_property_state SET verification_status = 'VERIFIED' WHERE state_id = 'TEST_ONLY_STATE_1'")
    result = conn.execute("SELECT verification_status FROM canonical_property_state WHERE state_id = 'TEST_ONLY_STATE_1'").fetchone()[0]
    assert result == "VERIFIED"
    print("PASS: VERIFIED update succeeds once active-evidence support AND a confirmed parcel match both exist")


def test_quarantine_blocks_new_support_for_canonical_state():
    """Quarantined evidence cannot support a NEW canonical state (via a new canonical_state_support link)."""
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn)
    conn.execute(
        "INSERT INTO canonical_property_state (state_id, parcel_id, version, as_of, fields_json, lifecycle_status) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_STATE_1", "TEST_ONLY_PARCEL_1", 1, NOW, "{}", "draft"),
    )
    conn.execute(
        "INSERT INTO evidence_disposition (disposition_id, evidence_id, disposition, set_at, reason) VALUES (?,?,?,?,?)",
        ("TEST_ONLY_DISP_1", "TEST_ONLY_EV_1", "QUARANTINED", NOW, "TEST_ONLY reason"),
    )
    try:
        conn.execute(
            "INSERT INTO canonical_state_support (support_id, canonical_property_state_id, observation_id, created_at) VALUES (?,?,?,?)",
            ("TEST_ONLY_SUP_BAD", "TEST_ONLY_STATE_1", "TEST_ONLY_OBS_1", NOW),
        )
        raise AssertionError("Expected sqlite3.IntegrityError - the observation's evidence is quarantined")
    except sqlite3.IntegrityError:
        pass
    print("PASS: quarantined evidence cannot newly support a canonical state")


def test_verification_does_not_retroactively_invalidate_but_view_reflects_current_support():
    """
    Honesty check: quarantining evidence AFTER a state is VERIFIED does not
    change the stored verification_status (no silent mutation - the row is
    what it is), but v_canonical_state_currently_supported correctly
    reports the support has lapsed. Both facts are asserted explicitly so
    neither is accidentally claimed to be the other.
    """
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn)
    conn.execute(
        "INSERT INTO canonical_property_state (state_id, parcel_id, version, as_of, fields_json, lifecycle_status) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_STATE_1", "TEST_ONLY_PARCEL_1", 1, NOW, "{}", "draft"),
    )
    conn.execute(
        "INSERT INTO canonical_state_support (support_id, canonical_property_state_id, observation_id, created_at) VALUES (?,?,?,?)",
        ("TEST_ONLY_SUP_1", "TEST_ONLY_STATE_1", "TEST_ONLY_OBS_1", NOW),
    )
    conn.execute(
        "INSERT INTO parcel_matches (match_id, observation_id, parcel_id, match_method, match_confidence, status) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_MATCH_1", "TEST_ONLY_OBS_1", "TEST_ONLY_PARCEL_1", "exact_identifier", 1.0, "confirmed"),
    )
    conn.execute("UPDATE canonical_property_state SET verification_status = 'VERIFIED' WHERE state_id = 'TEST_ONLY_STATE_1'")

    # Quarantine AFTER verification.
    conn.execute(
        "INSERT INTO evidence_disposition (disposition_id, evidence_id, disposition, set_at, reason) VALUES (?,?,?,?,?)",
        ("TEST_ONLY_DISP_1", "TEST_ONLY_EV_1", "QUARANTINED", NOW, "TEST_ONLY reason, set after verification"),
    )

    stored = conn.execute("SELECT verification_status FROM canonical_property_state WHERE state_id = 'TEST_ONLY_STATE_1'").fetchone()[0]
    assert stored == "VERIFIED", "stored verification_status must NOT be silently changed by a later quarantine"

    view_row = conn.execute(
        "SELECT stored_verification_status, has_active_support FROM v_canonical_state_currently_supported WHERE state_id = 'TEST_ONLY_STATE_1'"
    ).fetchone()
    assert view_row == ("VERIFIED", 0), f"expected the view to report stale support (has_active_support=0), got {view_row}"
    print("PASS: stored VERIFIED status is not retroactively changed; v_canonical_state_currently_supported correctly flags the lapsed support")


# ── Unmatched observation (re-verified at the DB level, not just dataclass level) ──

def test_unmatched_observation_remains_valid_without_a_parcel_claim():
    conn = _fresh_conn()
    _seed_minimal_chain(conn)
    _seed_one_observation(conn)
    conn.execute(
        "INSERT INTO parcel_matches (match_id, observation_id, parcel_id, match_method, match_confidence, status) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_MATCH_UNMATCHED", "TEST_ONLY_OBS_1", None, "unmatched", 0.0, "pending"),
    )
    row = conn.execute("SELECT parcel_id, match_method, status FROM parcel_matches WHERE match_id = 'TEST_ONLY_MATCH_UNMATCHED'").fetchone()
    assert row == (None, "unmatched", "pending")
    print("PASS: an unmatched observation's parcel_matches row is valid with parcel_id=NULL - no parcel claim created")


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
