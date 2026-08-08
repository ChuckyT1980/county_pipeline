"""
Tests for property_intelligence_v2's ONE canonical schema
(migrations/001_initial_schema.sql, applied via migrations/apply_schema.py).

No separate test schema exists - every test here applies the exact same
migration file production code would apply, to a temporary in-memory
SQLite database (sqlite3.connect(":memory:")) that is discarded when the
test ends. Never creates, opens, or writes to any file on disk.

All fixture values use an explicit TEST_ONLY_ prefix so a reviewer (or a
future accidental copy-paste into real code) can immediately recognize
them as placeholders, not real or synthetic California county data.

The job of this file is specifically to prove the schema REJECTS invalid
states (missing required fields, out-of-vocabulary statuses, dangling
foreign keys, out-of-range values) - not just that valid rows insert.

Run: python3 property_intelligence_v2/tests/test_schema.py
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "migrations"))

from apply_schema import CURRENT_SCHEMA_VERSION, apply_schema, get_applied_version  # noqa: E402

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    return conn


# ── Schema application itself ────────────────────────────────────────────

def test_schema_applies_and_records_its_own_version():
    conn = _fresh_conn()
    assert get_applied_version(conn) == CURRENT_SCHEMA_VERSION
    print(f"PASS: migrations/001_initial_schema.sql applies cleanly to an in-memory db, version={CURRENT_SCHEMA_VERSION}")


def test_foreign_keys_are_enforced():
    conn = _fresh_conn()
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk_status == 1, "PRAGMA foreign_keys must be ON for the rejection tests below to mean anything"
    print("PASS: PRAGMA foreign_keys = ON is active on the test connection")


def test_all_nine_entity_tables_exist():
    conn = _fresh_conn()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    expected = {
        "source_registry", "ingestion_runs", "raw_evidence", "observations",
        "parcels", "parcel_matches", "canonical_property_state",
        "reconciliation_feedback", "exceptions",
    }
    missing = expected - tables
    assert not missing, f"Missing tables: {missing}"
    print(f"PASS: all 9 entity tables present")


def test_apply_schema_is_idempotent():
    conn = _fresh_conn()
    apply_schema(conn)  # second call must not error or duplicate the migration row
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    assert len(rows) == 1, f"schema_migrations should have exactly 1 row for version 1, got {len(rows)}"
    print("PASS: re-applying the schema is idempotent")


# ── Valid round trip (establishes a baseline before the rejection tests) ─

def _insert_valid_chain(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO source_registry (source_id, county, county_fips, source_type, name, base_url, access_level, registered_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ("TEST_ONLY_SRC_1", "TEST_ONLY_COUNTY", "000", "assessor", "TEST_ONLY Assessor Search", "https://example.invalid", "full", NOW),
    )
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status, finished_at, next_action) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW, "succeeded", NOW, "none"),
    )
    conn.execute(
        "INSERT INTO raw_evidence (evidence_id, ingestion_run_id, source_id, retrieved_at, content_hash, content_type, source_url_or_identifier) "
        "VALUES (?,?,?,?,?,?,?)",
        ("TEST_ONLY_EV_1", "TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW, "0" * 64, "text/html", "https://example.invalid/page"),
    )
    conn.execute(
        "INSERT INTO observations (observation_id, evidence_id, observed_at, county, source_identifier_type, source_identifier_value, field_name, field_value, confidence) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("TEST_ONLY_OBS_1", "TEST_ONLY_EV_1", NOW, "TEST_ONLY_COUNTY", "test_identifier", "TEST_ONLY-000-000-000", "owner_name", "TEST_ONLY OWNER", "confirmed"),
    )
    conn.execute(
        "INSERT INTO parcels (parcel_id, county, county_fips, created_at, status) VALUES (?,?,?,?,?)",
        ("TEST_ONLY_PARCEL_1", "TEST_ONLY_COUNTY", "000", NOW, "active"),
    )
    conn.execute(
        "INSERT INTO parcel_matches (match_id, observation_id, parcel_id, match_method, match_confidence, status, matched_at) VALUES (?,?,?,?,?,?,?)",
        ("TEST_ONLY_MATCH_1", "TEST_ONLY_OBS_1", "TEST_ONLY_PARCEL_1", "exact_identifier", 1.0, "confirmed", NOW),
    )
    fields_json = json.dumps({"owner_name": {"value": "TEST_ONLY OWNER", "confidence": "confirmed", "source_observation_ids": ["TEST_ONLY_OBS_1"], "last_reconciled_at": NOW}})
    conn.execute(
        "INSERT INTO canonical_property_state (state_id, parcel_id, version, as_of, fields_json, lifecycle_status) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_STATE_1", "TEST_ONLY_PARCEL_1", 1, NOW, fields_json, "reconciled"),
    )
    conn.execute(
        "INSERT INTO reconciliation_feedback (feedback_id, canonical_property_state_id, observation_ids_considered_json, resolved_at, resolution_method, conflicts_detected_json) VALUES (?,?,?,?,?,?)",
        ("TEST_ONLY_FB_1", "TEST_ONLY_STATE_1", json.dumps(["TEST_ONLY_OBS_1"]), NOW, "most_recent", json.dumps([])),
    )
    conn.execute(
        "INSERT INTO exceptions (exception_id, occurred_at, stage, related_entity_type, related_entity_id, classification, severity, next_action, status) VALUES (?,?,?,?,?,?,?,?,?)",
        ("TEST_ONLY_EXC_1", NOW, "ingestion", "ingestion_run", "TEST_ONLY_RUN_1", "transient_error", "low", "none", "resolved"),
    )
    conn.commit()


def test_valid_chain_round_trips_end_to_end():
    conn = _fresh_conn()
    _insert_valid_chain(conn)
    row = conn.execute(
        """
        SELECT p.parcel_id, o.field_value, e.source_url_or_identifier, ir.status, sr.name
        FROM parcel_matches pm
        JOIN parcels p ON p.parcel_id = pm.parcel_id
        JOIN observations o ON o.observation_id = pm.observation_id
        JOIN raw_evidence e ON e.evidence_id = o.evidence_id
        JOIN ingestion_runs ir ON ir.run_id = e.ingestion_run_id
        JOIN source_registry sr ON sr.source_id = ir.source_id
        WHERE p.parcel_id = 'TEST_ONLY_PARCEL_1'
        """
    ).fetchone()
    assert row == ("TEST_ONLY_PARCEL_1", "TEST_ONLY OWNER", "https://example.invalid/page", "succeeded", "TEST_ONLY Assessor Search"), row
    print("PASS: a valid TEST_ONLY chain (source_registry -> ... -> parcels) round-trips end to end")


# ── Rejection tests: the actual point of this file ───────────────────────

def test_rejects_dangling_foreign_key():
    conn = _fresh_conn()
    try:
        conn.execute(
            "INSERT INTO parcel_matches (match_id, observation_id, parcel_id, match_method, match_confidence, status) VALUES (?,?,?,?,?,?)",
            ("TEST_ONLY_MATCH_BAD", "TEST_ONLY_OBS_DOES_NOT_EXIST", None, "unmatched", 0.0, "pending"),
        )
        conn.commit()
        raise AssertionError("Expected sqlite3.IntegrityError for a dangling observation_id foreign key")
    except sqlite3.IntegrityError:
        pass
    print("PASS: a parcel_matches row with a dangling observation_id foreign key is rejected")


def test_rejects_out_of_vocabulary_status():
    conn = _fresh_conn()
    _insert_valid_chain(conn)
    try:
        conn.execute(
            "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
            ("TEST_ONLY_RUN_BAD", "TEST_ONLY_SRC_1", NOW, "definitely_not_a_real_status"),
        )
        conn.commit()
        raise AssertionError("Expected sqlite3.IntegrityError for an out-of-vocabulary ingestion_runs.status")
    except sqlite3.IntegrityError:
        pass
    print("PASS: an out-of-vocabulary status value is rejected by the CHECK constraint")


def test_rejects_missing_required_field():
    conn = _fresh_conn()
    try:
        # source_type is NOT NULL - omit it entirely.
        conn.execute(
            "INSERT INTO source_registry (source_id, county, county_fips, name, access_level, registered_at) VALUES (?,?,?,?,?,?)",
            ("TEST_ONLY_SRC_BAD", "TEST_ONLY_COUNTY", "000", "TEST_ONLY Missing Type Source", "full", NOW),
        )
        conn.commit()
        raise AssertionError("Expected sqlite3.IntegrityError for a NULL source_type")
    except sqlite3.IntegrityError:
        pass
    print("PASS: a NULL value for a NOT NULL column (source_type) is rejected")


def test_rejects_match_confidence_out_of_range():
    conn = _fresh_conn()
    _insert_valid_chain(conn)
    try:
        conn.execute(
            "INSERT INTO parcel_matches (match_id, observation_id, parcel_id, match_method, match_confidence, status) VALUES (?,?,?,?,?,?)",
            ("TEST_ONLY_MATCH_BAD_CONF", "TEST_ONLY_OBS_1", "TEST_ONLY_PARCEL_1", "fuzzy", 1.5, "pending"),
        )
        conn.commit()
        raise AssertionError("Expected sqlite3.IntegrityError for match_confidence > 1.0")
    except sqlite3.IntegrityError:
        pass
    print("PASS: match_confidence outside [0.0, 1.0] is rejected by the CHECK constraint")


def test_rejects_duplicate_canonical_state_version():
    """UNIQUE(parcel_id, version) - two canonical states can't claim the
    same version number for the same parcel."""
    conn = _fresh_conn()
    _insert_valid_chain(conn)  # already inserts TEST_ONLY_STATE_1 at version=1 for TEST_ONLY_PARCEL_1
    try:
        conn.execute(
            "INSERT INTO canonical_property_state (state_id, parcel_id, version, as_of, fields_json, lifecycle_status) VALUES (?,?,?,?,?,?)",
            ("TEST_ONLY_STATE_DUPLICATE", "TEST_ONLY_PARCEL_1", 1, NOW, "{}", "draft"),
        )
        conn.commit()
        raise AssertionError("Expected sqlite3.IntegrityError for a duplicate (parcel_id, version)")
    except sqlite3.IntegrityError:
        pass
    print("PASS: a duplicate (parcel_id, version) in canonical_property_state is rejected by the UNIQUE constraint")


def test_rejects_evidence_referencing_wrong_source_after_run_deleted_scenario_is_not_applicable():
    """
    Placeholder documenting a deliberate Phase 1 scope boundary: this
    schema does NOT enforce that raw_evidence.source_id matches
    raw_evidence.ingestion_run_id's own source_id (a cross-column
    consistency rule, not expressible as a simple FK or CHECK in SQLite).
    Recorded here as a known, explicit limitation rather than silently
    assumed to be covered - future work for either application-level
    validation or a stricter schema revision.
    """
    print("PASS (documented limitation, not a bug): cross-column source_id consistency between "
          "raw_evidence and its ingestion_run is not enforced at the schema level in Phase 1")


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
