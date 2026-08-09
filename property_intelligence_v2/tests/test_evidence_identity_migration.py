"""
Tests for property_intelligence_v2/migrations/003_evidence_identity_unique.sql.

Applies migrations via apply_schema, the same single code path production
code would use, to a fresh temporary in-memory SQLite database for every
test. Never touches a file on disk. All fixture values use an explicit
TEST_ONLY_ prefix.

Proves: the evidence-identity key is (source_id, content_hash,
source_url_or_identifier) - not bare content_hash - both by rejecting
duplicates of that triple and by explicitly allowing byte-identical content
from a different source_url_or_identifier. Also proves 003's preflight
check (apply_schema.py's _preflight_003) fails clearly, before the index is
even created, if pre-existing rows already violate it.

Run: python3 property_intelligence_v2/tests/test_evidence_identity_migration.py
"""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "migrations"))

from apply_schema import apply_schema, get_applied_version  # noqa: E402

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()


def _conn_at_version_2() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn, target_version=2)
    return conn


def _seed_source_and_run(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO source_registry (source_id, county, county_fips, source_type, name, base_url, access_level, registered_at) VALUES (?,?,?,?,?,?,?,?)",
        ("TEST_ONLY_SRC_1", "TEST_ONLY_COUNTY", "000", "assessor", "TEST_ONLY Source", "https://example.invalid", "full", NOW),
    )
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        ("TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW, "succeeded"),
    )
    conn.commit()


def _insert_evidence(conn: sqlite3.Connection, evidence_id: str, content_hash: str, source_url: str) -> None:
    conn.execute(
        "INSERT INTO raw_evidence (evidence_id, ingestion_run_id, source_id, retrieved_at, content_hash, content_type, source_url_or_identifier) VALUES (?,?,?,?,?,?,?)",
        (evidence_id, "TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW, content_hash, "text/html", source_url),
    )


def test_preflight_blocks_migration_003_when_duplicates_already_exist():
    conn = _conn_at_version_2()
    _seed_source_and_run(conn)
    # Two rows sharing the full (source_id, content_hash, source_url_or_identifier)
    # triple - legal at version 2, since no uniqueness constraint exists yet.
    _insert_evidence(conn, "TEST_ONLY_EV_1", "a" * 64, "https://example.invalid/doc")
    _insert_evidence(conn, "TEST_ONLY_EV_2", "a" * 64, "https://example.invalid/doc")
    conn.commit()
    try:
        apply_schema(conn, target_version=3)
        raise AssertionError("Expected RuntimeError from migration 003's preflight check")
    except RuntimeError as e:
        assert "preflight failed" in str(e)
    assert get_applied_version(conn) == 2, "version 3 must not be recorded as applied when its preflight fails"
    print("PASS: migration 003 preflight blocks application when duplicate identity rows already exist")


def test_migration_003_applies_cleanly_with_no_duplicates():
    conn = _conn_at_version_2()
    _seed_source_and_run(conn)
    _insert_evidence(conn, "TEST_ONLY_EV_1", "b" * 64, "https://example.invalid/doc")
    conn.commit()
    apply_schema(conn, target_version=3)
    assert get_applied_version(conn) == 3
    print("PASS: migration 003 applies cleanly when no duplicate identity rows exist")


def test_unique_index_rejects_duplicate_identity_at_insert_time():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)  # default target - includes 003
    _seed_source_and_run(conn)
    _insert_evidence(conn, "TEST_ONLY_EV_1", "c" * 64, "https://example.invalid/doc")
    conn.commit()
    try:
        _insert_evidence(conn, "TEST_ONLY_EV_2", "c" * 64, "https://example.invalid/doc")
        conn.commit()
        raise AssertionError("Expected sqlite3.IntegrityError for a duplicate (source_id, content_hash, source_url_or_identifier)")
    except sqlite3.IntegrityError:
        pass
    print("PASS: a second raw_evidence row with the identical identity triple is rejected")


def test_unique_index_allows_same_hash_different_source_url():
    """The evidence-identity decision itself: identical bytes from a DIFFERENT
    source_url_or_identifier must be allowed as a distinct record."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    _seed_source_and_run(conn)
    _insert_evidence(conn, "TEST_ONLY_EV_1", "d" * 64, "https://example.invalid/doc-A")
    _insert_evidence(conn, "TEST_ONLY_EV_2", "d" * 64, "https://example.invalid/doc-B")
    conn.commit()
    rows = conn.execute("SELECT evidence_id FROM raw_evidence WHERE content_hash = ?", ("d" * 64,)).fetchall()
    assert len(rows) == 2, "byte-identical content from two different source_url_or_identifier values must both persist"
    print("PASS: byte-identical content from a different source_url_or_identifier is stored as a distinct record")


class _FailingMetadataInsertConnection:
    """Wraps a real sqlite3.Connection. Passes every call straight through to
    it, except: the first time it sees the schema_migrations INSERT, it
    raises instead of running it - simulating a controlled failure between a
    migration's DDL succeeding and its metadata row being recorded, without
    needing real concurrency or a corrupted database file. Used only by
    test_migration_003_leaves_no_partial_state_after_controlled_metadata_failure
    below; apply_schema() itself is unaware this wrapper exists - it only
    ever calls plain execute()/executescript()/commit()/rollback()."""

    def __init__(self, real_conn: sqlite3.Connection):
        self._real = real_conn

    def execute(self, sql, params=()):
        if "INSERT INTO schema_migrations" in sql:
            raise sqlite3.OperationalError("SIMULATED: metadata insert failure for durability test")
        return self._real.execute(sql, params)

    def executescript(self, sql):
        return self._real.executescript(sql)

    def commit(self):
        return self._real.commit()

    def rollback(self):
        return self._real.rollback()

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_migration_003_leaves_no_partial_state_after_controlled_metadata_failure():
    """Proves migration 003 can never be left as 'index exists but version
    absent': forces the schema_migrations INSERT to fail after 003's DDL
    (CREATE UNIQUE INDEX) would otherwise have succeeded, and asserts BOTH
    the index and the schema_migrations row are absent afterward - not just
    that the row is missing (which would also be true if apply_schema simply
    skipped the insert on failure without rolling back the DDL)."""
    real_conn = sqlite3.connect(":memory:")
    real_conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(real_conn, target_version=2)

    wrapped = _FailingMetadataInsertConnection(real_conn)
    try:
        apply_schema(wrapped, target_version=3)
        raise AssertionError("Expected the simulated metadata-insert failure to propagate")
    except sqlite3.OperationalError as e:
        assert "SIMULATED" in str(e)

    idx_count = real_conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='idx_raw_evidence_identity'"
    ).fetchone()[0]
    assert idx_count == 0, "the index must not exist when its schema_migrations row failed to commit - no partial state"
    assert get_applied_version(real_conn) == 2, "version 3 must not be recorded as applied"

    # And apply_schema must still be able to apply 003 cleanly afterward - no
    # corrupted state (e.g. a half-created index) blocking a normal retry.
    apply_schema(real_conn, target_version=3)
    assert get_applied_version(real_conn) == 3
    idx_count_after_retry = real_conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='idx_raw_evidence_identity'"
    ).fetchone()[0]
    assert idx_count_after_retry == 1
    print("PASS: a controlled failure between migration 003's DDL and its schema_migrations insert leaves neither applied, and a clean retry succeeds afterward")


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
