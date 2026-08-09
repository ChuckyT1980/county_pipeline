"""
Tests for property_intelligence_v2/importers/legacy_evidence_importer.py.

Applies migrations 001-003 (via apply_schema, the same single code path
production code would use) to a fresh temporary in-memory SQLite database
for every test. Never touches a file on disk under the real repository -
all artifact writes go to a tempfile.TemporaryDirectory() created and torn
down per test, and path-manifest tests that need a fake repo layout build
one under a second tempfile.TemporaryDirectory() rather than touching the
real kern/butte/lake/del_norte folders.

A DELIBERATE, NARROW EXCEPTION to the repo's TEST_ONLY_ fixture-prefix
convention: legacy_evidence_importer.reject_test_only() is a production
safety gate that refuses to persist any value containing "TEST_ONLY_" -
so tests that exercise the importer's actual SUCCESS path (rather than
this rejection itself) cannot use TEST_ONLY_-prefixed county /
source_url_or_identifier / content_type / file-content values without
tripping the very gate being tested around. Those specific tests instead
use obviously-synthetic, non-California, RFC 2606-reserved values
(county="EXAMPLE_COUNTY", URLs under https://example.invalid/) - clearly
marked in each such test's docstring. source_id/ingestion_run_id/run_id
are NOT covered by reject_test_only (they reference pre-existing rows this
module never creates) and keep the normal TEST_ONLY_ prefix throughout.

Run: python3 property_intelligence_v2/tests/test_legacy_evidence_importer.py
"""
import hashlib
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "migrations"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "importers"))

from apply_schema import apply_schema  # noqa: E402
import legacy_evidence_importer as importer  # noqa: E402
from legacy_evidence_importer import (  # noqa: E402
    ImporterConfigError,
    ImporterIdentityError,
    ImporterInputError,
    ImportFinalizationError,
    ImportTransactionError,
    ObservationFieldInput,
    UnknownSourceError,
    content_addressed_path,
    get_repo_root,
    import_evidence_record,
    resolve_artifact_root,
    run_legacy_import,
    validate_artifact_root,
    validate_legacy_input_path,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()

IMPORTER_SOURCE = Path(importer.__file__).read_text(encoding="utf-8")


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)  # 001+002+003, the one shared code path
    return conn


def _seed_source(conn: sqlite3.Connection, source_id: str = "TEST_ONLY_SRC_1") -> None:
    conn.execute(
        "INSERT INTO source_registry (source_id, county, county_fips, source_type, name, base_url, access_level, registered_at) VALUES (?,?,?,?,?,?,?,?)",
        (source_id, "TEST_ONLY_COUNTY", "000", "assessor", "TEST_ONLY Source", "https://example.invalid", "full", NOW_ISO),
    )
    conn.commit()


class _TempLayout:
    """A throwaway artifact_root dir plus a throwaway fake-repo dir with a
    kern/ subfolder containing one real fixture file. Neither ever touches
    the real repository."""

    def __enter__(self):
        self._tmp = tempfile.mkdtemp(prefix="piv2_importer_test_")
        self.tmp = Path(self._tmp)
        self.artifact_root = self.tmp / "artifacts"
        self.fake_repo = self.tmp / "fake_repo"
        (self.fake_repo / "kern").mkdir(parents=True)
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self._tmp, ignore_errors=True)


# ── resolve_artifact_root ───────────────────────────────────────────────

def test_resolve_artifact_root_requires_env_var():
    try:
        resolve_artifact_root(env={})
        raise AssertionError("Expected ImporterConfigError")
    except ImporterConfigError:
        pass
    print("PASS: resolve_artifact_root requires PIV2_ARTIFACT_ROOT to be set")


def test_resolve_artifact_root_requires_absolute_path():
    try:
        resolve_artifact_root(env={"PIV2_ARTIFACT_ROOT": "relative/path"})
        raise AssertionError("Expected ImporterConfigError")
    except ImporterConfigError:
        pass
    print("PASS: resolve_artifact_root rejects a relative path")


def test_resolve_artifact_root_rejects_path_inside_repo():
    inside = str(get_repo_root() / "property_intelligence_v2" / "TEST_ONLY_artifacts")
    try:
        resolve_artifact_root(env={"PIV2_ARTIFACT_ROOT": inside})
        raise AssertionError("Expected ImporterConfigError")
    except ImporterConfigError:
        pass
    print("PASS: resolve_artifact_root rejects an artifact root inside the repository")


def test_resolve_artifact_root_accepts_valid_absolute_outside_repo_path():
    with tempfile.TemporaryDirectory() as d:
        result = resolve_artifact_root(env={"PIV2_ARTIFACT_ROOT": d})
        assert result == Path(d).resolve()
    print("PASS: resolve_artifact_root accepts a valid absolute path outside the repository")


def test_validate_artifact_root_rejects_relative_and_inside_repo_directly():
    """validate_artifact_root() itself, in isolation - the shared function
    resolve_artifact_root() now delegates to, and that import_evidence_record()/
    run_legacy_import() call directly."""
    try:
        validate_artifact_root("relative/path")
        raise AssertionError("Expected ImporterConfigError")
    except ImporterConfigError:
        pass
    try:
        validate_artifact_root(get_repo_root() / "property_intelligence_v2" / "TEST_ONLY_artifacts")
        raise AssertionError("Expected ImporterConfigError")
    except ImporterConfigError:
        pass
    with tempfile.TemporaryDirectory() as d:
        assert validate_artifact_root(d) == Path(d).resolve()
    print("PASS: validate_artifact_root rejects relative and in-repo paths directly, accepts a valid external path")


# ── Phase 2.2: entry points can no longer bypass artifact-root isolation ──

def test_import_evidence_record_rejects_artifact_root_inside_repo():
    """Direct-import case (A): import_evidence_record() itself must reject
    an artifact_root inside the repository, before any artifact write or
    DB insert - not just resolve_artifact_root(), which this call never
    goes through."""
    conn = _fresh_conn()
    _seed_source(conn)
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        ("TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW_ISO, "attempted"),
    )
    conn.commit()
    with _TempLayout() as t:
        fixture = t.fake_repo / "kern" / "doc.html"
        fixture.write_bytes(b"<html>fixture</html>")
        inside_repo_artifact_root = get_repo_root() / "property_intelligence_v2" / "TEST_ONLY_direct_artifacts_should_never_exist"
        try:
            import_evidence_record(
                conn, ingestion_run_id="TEST_ONLY_RUN_1", source_id="TEST_ONLY_SRC_1", county="EXAMPLE_COUNTY",
                legacy_path=fixture, source_url_or_identifier="https://example.invalid/doc",
                content_type="text/html", artifact_root=inside_repo_artifact_root, repo_root=t.fake_repo, now=NOW,
            )
            raise AssertionError("Expected ImporterConfigError")
        except ImporterConfigError:
            pass
        assert not inside_repo_artifact_root.exists(), "no artifact directory should ever have been created inside the repository"
        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0, "no raw_evidence row may exist"
    print("PASS: import_evidence_record rejects an artifact_root inside the repository before any artifact write or DB insert")


def test_run_legacy_import_rejects_artifact_root_inside_repo_before_phase_a():
    """Batch-import case (B): run_legacy_import() must reject an in-repo
    artifact_root BEFORE Phase A creates/commits an ingestion_runs row -
    zero ingestion_runs rows must exist afterward, not a row left dangling
    because Phase A already ran."""
    conn = _fresh_conn()
    _seed_source(conn)
    with _TempLayout() as t:
        fixture = t.fake_repo / "kern" / "doc.html"
        fixture.write_bytes(b"<html>fixture</html>")
        inside_repo_artifact_root = get_repo_root() / "property_intelligence_v2" / "TEST_ONLY_batch_artifacts_should_never_exist"
        try:
            run_legacy_import(
                conn, source_id="TEST_ONLY_SRC_1", county="EXAMPLE_COUNTY",
                records=[{
                    "legacy_path": fixture, "source_url_or_identifier": "https://example.invalid/doc",
                    "content_type": "text/html",
                }],
                artifact_root=inside_repo_artifact_root, repo_root=t.fake_repo, now=NOW,
            )
            raise AssertionError("Expected ImporterConfigError")
        except ImporterConfigError:
            pass
        assert not inside_repo_artifact_root.exists(), "no artifact directory should ever have been created inside the repository"
        assert conn.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0] == 0, "Phase A must not have run"
    print("PASS: run_legacy_import rejects an artifact_root inside the repository before Phase A creates any ingestion_runs row")


def test_valid_external_artifact_root_still_succeeds_direct_and_batch():
    """Case (C): a valid, external, absolute artifact_root still succeeds
    through both import_evidence_record() and run_legacy_import() - the new
    validation does not break the legitimate path."""
    conn = _fresh_conn()
    _seed_source(conn)
    with _TempLayout() as t:
        conn.execute(
            "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
            ("TEST_ONLY_RUN_DIRECT", "TEST_ONLY_SRC_1", NOW_ISO, "attempted"),
        )
        conn.commit()
        direct_fixture = t.fake_repo / "kern" / "direct.html"
        direct_fixture.write_bytes(b"<html>direct path fixture</html>")
        direct_result = import_evidence_record(
            conn, ingestion_run_id="TEST_ONLY_RUN_DIRECT", source_id="TEST_ONLY_SRC_1", county="EXAMPLE_COUNTY",
            legacy_path=direct_fixture, source_url_or_identifier="https://example.invalid/direct",
            content_type="text/html", artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )
        assert direct_result.artifact_written is True
        assert direct_result.artifact_path.exists()

        batch_fixture = t.fake_repo / "kern" / "batch.html"
        batch_fixture.write_bytes(b"<html>batch path fixture</html>")
        batch_result = run_legacy_import(
            conn, source_id="TEST_ONLY_SRC_1", county="EXAMPLE_COUNTY",
            records=[{
                "legacy_path": batch_fixture, "source_url_or_identifier": "https://example.invalid/batch",
                "content_type": "text/html",
            }],
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )
        assert batch_result.status == "succeeded"
        assert len(batch_result.succeeded) == 1
        assert batch_result.succeeded[0].artifact_path.exists()
    print("PASS: a valid, external, absolute artifact_root still succeeds through both import_evidence_record and run_legacy_import")


# ── validate_legacy_input_path (pure path checks - no filesystem writes) ──

def test_validate_legacy_input_path_accepts_allowed_manifest_roots():
    for root in ("kern", "butte", "lake", "del_norte"):
        # Nonexistent probe filename - path-string validation only, no file is read.
        validate_legacy_input_path(get_repo_root() / root / "TEST_ONLY_probe_nonexistent.html")
    print("PASS: validate_legacy_input_path accepts all four allowed manifest roots")


def test_validate_legacy_input_path_rejects_denied_directories():
    for bad in ("monitor_runs", "output"):
        try:
            validate_legacy_input_path(get_repo_root() / bad / "TEST_ONLY_probe.html")
            raise AssertionError(f"Expected ImporterInputError for {bad!r}")
        except ImporterInputError:
            pass
    # nested under an allowed root too
    try:
        validate_legacy_input_path(get_repo_root() / "kern" / "dashboards" / "TEST_ONLY_probe.html")
        raise AssertionError("Expected ImporterInputError for a nested dashboards/ path")
    except ImporterInputError:
        pass
    print("PASS: validate_legacy_input_path rejects monitor_runs/, output/, and nested denied directories")


def test_validate_legacy_input_path_rejects_outside_repo():
    try:
        validate_legacy_input_path(Path("/tmp/TEST_ONLY_not_in_repo.html"))
        raise AssertionError("Expected ImporterInputError")
    except ImporterInputError:
        pass
    print("PASS: validate_legacy_input_path rejects a path entirely outside the repository")


# ── reject_test_only ────────────────────────────────────────────────────

def test_reject_test_only_detects_marker_in_any_named_field():
    try:
        importer.reject_test_only(county="TEST_ONLY_COUNTY", other="fine")
        raise AssertionError("Expected ImporterIdentityError")
    except ImporterIdentityError:
        pass
    importer.reject_test_only(county="EXAMPLE_COUNTY", other="also fine")  # must not raise
    print("PASS: reject_test_only flags any named field containing the marker, passes clean values")


# ── import_evidence_record: rejections ──────────────────────────────────

def test_import_rejects_unknown_source_registry():
    conn = _fresh_conn()
    with _TempLayout() as t:
        fixture = t.fake_repo / "kern" / "doc.html"
        fixture.write_bytes(b"<html>fixture</html>")
        try:
            import_evidence_record(
                conn, ingestion_run_id="TEST_ONLY_RUN_1", source_id="TEST_ONLY_SRC_UNKNOWN",
                county="EXAMPLE_COUNTY", legacy_path=fixture,
                source_url_or_identifier="https://example.invalid/doc", content_type="text/html",
                artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
            )
            raise AssertionError("Expected UnknownSourceError")
        except UnknownSourceError:
            pass
        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
    print("PASS: import_evidence_record rejects an unknown source_id and persists nothing")


def test_import_rejects_test_only_marked_value_before_any_side_effect():
    conn = _fresh_conn()
    _seed_source(conn)
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        ("TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW_ISO, "attempted"),
    )
    conn.commit()
    with _TempLayout() as t:
        fixture = t.fake_repo / "kern" / "doc.html"
        fixture.write_bytes(b"<html>fixture</html>")
        try:
            import_evidence_record(
                conn, ingestion_run_id="TEST_ONLY_RUN_1", source_id="TEST_ONLY_SRC_1",
                county="TEST_ONLY_COUNTY", legacy_path=fixture,
                source_url_or_identifier="https://example.invalid/doc", content_type="text/html",
                artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
            )
            raise AssertionError("Expected ImporterIdentityError")
        except ImporterIdentityError:
            pass
        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
        assert not any(t.artifact_root.rglob("*")), "no artifact should be written when a value is rejected"
    print("PASS: a TEST_ONLY_-marked value is rejected before hashing, artifact write, or DB insert")


# ── import_evidence_record: happy path (non-TEST_ONLY_ synthetic content - see module docstring) ──

def test_import_happy_path_writes_artifact_and_records_transactionally():
    """Uses county='EXAMPLE_COUNTY' and https://example.invalid/, not TEST_ONLY_,
    specifically to prove the pipeline succeeds when reject_test_only's gate
    correctly passes clean input through - see this file's module docstring."""
    conn = _fresh_conn()
    _seed_source(conn)
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        ("TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW_ISO, "attempted"),
    )
    conn.commit()
    with _TempLayout() as t:
        content = b"<html>importer fixture body</html>"
        fixture = t.fake_repo / "kern" / "doc.html"
        fixture.write_bytes(content)

        result = import_evidence_record(
            conn, ingestion_run_id="TEST_ONLY_RUN_1", source_id="TEST_ONLY_SRC_1",
            county="EXAMPLE_COUNTY", legacy_path=fixture,
            source_url_or_identifier="https://example.invalid/doc", content_type="text/html",
            observation_fields=(ObservationFieldInput("owner_name", "EXAMPLE OWNER", "confirmed"),),
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )

        assert result.artifact_written is True
        assert result.deduplicated is False
        assert result.artifact_path.read_bytes() == content
        expected_hash = hashlib.sha256(content).hexdigest()
        assert result.artifact_path == content_addressed_path(t.artifact_root, "EXAMPLE_COUNTY", expected_hash, "text/html")

        ev_row = conn.execute(
            "SELECT source_id, content_type, source_url_or_identifier FROM raw_evidence WHERE evidence_id = ?",
            (result.evidence_id,),
        ).fetchone()
        assert ev_row == ("TEST_ONLY_SRC_1", "text/html", "https://example.invalid/doc")

        disp = conn.execute(
            "SELECT current_disposition FROM v_evidence_current_disposition WHERE evidence_id = ?",
            (result.evidence_id,),
        ).fetchone()[0]
        assert disp == "ACTIVE"

        obs_row = conn.execute(
            "SELECT field_name, field_value, confidence FROM observations WHERE observation_id = ?",
            (result.observation_ids[0],),
        ).fetchone()
        assert obs_row == ("owner_name", "EXAMPLE OWNER", "confirmed")
    print("PASS: happy-path import writes a content-addressed artifact and records raw_evidence + disposition + observation transactionally")


def test_reimport_same_identity_is_deduplicated_not_duplicated():
    conn = _fresh_conn()
    _seed_source(conn)
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        ("TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW_ISO, "attempted"),
    )
    conn.commit()
    with _TempLayout() as t:
        fixture = t.fake_repo / "kern" / "doc.html"
        fixture.write_bytes(b"<html>dedup fixture</html>")
        kwargs = dict(
            ingestion_run_id="TEST_ONLY_RUN_1", source_id="TEST_ONLY_SRC_1", county="EXAMPLE_COUNTY",
            legacy_path=fixture, source_url_or_identifier="https://example.invalid/doc",
            content_type="text/html", artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )
        first = import_evidence_record(conn, **kwargs)
        second = import_evidence_record(conn, **kwargs)
        assert first.deduplicated is False
        assert second.deduplicated is True
        assert first.evidence_id == second.evidence_id
        count = conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0]
        assert count == 1, "a re-import with the identical identity triple must not create a second row"
    print("PASS: re-importing the same (source_id, content_hash, source_url_or_identifier) is deduplicated, not duplicated")


def test_concurrent_identity_conflict_forces_on_conflict_do_nothing_branch():
    """Forces the ON CONFLICT DO NOTHING branch itself, not the earlier
    sequential pre-check dedup path exercised by the test above. Uses a real
    on-disk SQLite file (not :memory:, which is not shared across separate
    connections) plus a second, genuine connection and the
    _test_only_race_hook seam (never used by production code - see
    import_evidence_record's own docstring) to commit the colliding row in
    the exact gap between this call's pre-check SELECT (which must see
    nothing) and its INSERT ... ON CONFLICT DO NOTHING (which must then hit
    a real conflict, detected via cursor.rowcount, not error-text matching)."""
    with _TempLayout() as t:
        db_path = t.tmp / "race.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        apply_schema(conn)
        _seed_source(conn)
        conn.execute(
            "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
            ("TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW_ISO, "attempted"),
        )
        conn.commit()

        content = b"<html>race fixture</html>"
        fixture = t.fake_repo / "kern" / "race.html"
        fixture.write_bytes(content)
        content_hash = hashlib.sha256(content).hexdigest()

        racer_conn = sqlite3.connect(str(db_path))
        racer_conn.execute("PRAGMA foreign_keys = ON")
        raced_evidence_id = "EV_RACE_WINNER"

        def _inject_concurrent_insert():
            racer_conn.execute(
                "INSERT INTO raw_evidence (evidence_id, ingestion_run_id, source_id, retrieved_at, "
                "content_hash, content_type, source_url_or_identifier, storage_path) VALUES (?,?,?,?,?,?,?,?)",
                (raced_evidence_id, "TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW_ISO, content_hash,
                 "text/html", "https://example.invalid/race", None),
            )
            racer_conn.commit()

        result = import_evidence_record(
            conn, ingestion_run_id="TEST_ONLY_RUN_1", source_id="TEST_ONLY_SRC_1", county="EXAMPLE_COUNTY",
            legacy_path=fixture, source_url_or_identifier="https://example.invalid/race",
            content_type="text/html", artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
            _test_only_race_hook=_inject_concurrent_insert,
        )

        assert result.deduplicated is True
        assert result.evidence_id == raced_evidence_id, "must resolve to the row the concurrent writer actually committed"
        count = conn.execute("SELECT COUNT(*) FROM raw_evidence WHERE content_hash = ?", (content_hash,)).fetchone()[0]
        assert count == 1, "the losing side's INSERT ... ON CONFLICT DO NOTHING must not have created a second row"
        racer_conn.close()
        conn.close()
    print("PASS: a genuine concurrent identity conflict (a second real connection committing between this call's pre-check and its INSERT) is resolved via ON CONFLICT DO NOTHING + rowcount + exact re-query")


def test_unrelated_integrity_error_is_not_treated_as_dedup():
    """A CHECK-constraint failure unrelated to the identity index (invalid
    observation confidence) must roll back the whole transaction and raise
    ImportTransactionError - never be silently treated as a duplicate."""
    conn = _fresh_conn()
    _seed_source(conn)
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        ("TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW_ISO, "attempted"),
    )
    conn.commit()
    with _TempLayout() as t:
        fixture = t.fake_repo / "kern" / "bad_confidence.html"
        fixture.write_bytes(b"<html>bad confidence fixture</html>")
        try:
            import_evidence_record(
                conn, ingestion_run_id="TEST_ONLY_RUN_1", source_id="TEST_ONLY_SRC_1", county="EXAMPLE_COUNTY",
                legacy_path=fixture, source_url_or_identifier="https://example.invalid/bad-confidence",
                content_type="text/html",
                observation_fields=(ObservationFieldInput("owner_name", "EXAMPLE OWNER", "NOT_A_REAL_CONFIDENCE_LEVEL"),),
                artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
            )
            raise AssertionError("Expected ImportTransactionError")
        except ImportTransactionError:
            pass
        count = conn.execute(
            "SELECT COUNT(*) FROM raw_evidence WHERE source_url_or_identifier = ?",
            ("https://example.invalid/bad-confidence",),
        ).fetchone()[0]
        assert count == 0, "the whole transaction, including raw_evidence, must roll back on an unrelated failure"
    print("PASS: an unrelated integrity error (invalid confidence) rolls back the whole transaction and raises ImportTransactionError, never treated as dedup")


# ── run_legacy_import: Phase A/B/C lifecycle + failure audit trail ────────

def test_run_legacy_import_phase_a_c_lifecycle_and_orphan_artifact_audit():
    conn = _fresh_conn()
    _seed_source(conn)
    with _TempLayout() as t:
        good = t.fake_repo / "kern" / "good.html"
        good.write_bytes(b"<html>good record</html>")
        bad = t.fake_repo / "kern" / "bad.html"
        bad.write_bytes(b"<html>bad record - fails at DB transaction time</html>")

        result = run_legacy_import(
            conn, source_id="TEST_ONLY_SRC_1", county="EXAMPLE_COUNTY",
            records=[
                {"legacy_path": good, "source_url_or_identifier": "https://example.invalid/good", "content_type": "text/html"},
                {
                    "legacy_path": bad, "source_url_or_identifier": "https://example.invalid/bad", "content_type": "text/html",
                    # Out-of-vocabulary confidence - violates observations' CHECK constraint,
                    # forcing a Phase B rollback AFTER the artifact has already been written.
                    "observation_fields": (ObservationFieldInput("owner_name", "EXAMPLE OWNER", "NOT_A_REAL_CONFIDENCE_LEVEL"),),
                },
            ],
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )

        assert result.status == "partial"
        assert len(result.succeeded) == 1
        assert len(result.failed) == 1

        run_row = conn.execute(
            "SELECT status, attempted_count, succeeded_count, failed_count FROM ingestion_runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert run_row == ("partial", 2, 1, 1)

        exc_row = conn.execute(
            "SELECT related_entity_type, related_entity_id, notes FROM exceptions WHERE related_entity_id = ?",
            (result.run_id,),
        ).fetchone()
        assert exc_row[0] == "ingestion_run"
        assert exc_row[1] == result.run_id
        assert "orphan_artifact_path=" in exc_row[2], "the exceptions audit row must name the orphaned artifact path"

        orphan_path = result.failed[0].orphan_artifact_path
        assert orphan_path is not None and orphan_path.exists(), "the orphaned artifact must remain on disk, not be deleted"

        bad_evidence_count = conn.execute(
            "SELECT COUNT(*) FROM raw_evidence WHERE source_url_or_identifier = ?", ("https://example.invalid/bad",)
        ).fetchone()[0]
        assert bad_evidence_count == 0, "the failed record's transaction must have rolled back with zero partial rows"
    print("PASS: run_legacy_import's Phase A/C lifecycle records a partial run and audits the orphaned artifact without any partial evidence row")


class _FailingExceptionsInsertConnection:
    """Wraps a real sqlite3.Connection. Passes every call straight through to
    it, except: the first time it sees an INSERT INTO exceptions statement,
    it raises instead of running it - simulating a failure during Phase C
    AFTER the ingestion_runs UPDATE has already executed (but not yet
    committed), without needing real concurrency or timing. Phase A and
    Phase B statements (INSERT INTO ingestion_runs, everything
    import_evidence_record does) are untouched by this wrapper - only the
    exceptions INSERT text is intercepted, and only in Phase C is that
    statement ever issued."""

    def __init__(self, real_conn: sqlite3.Connection):
        self._real = real_conn

    def execute(self, sql, params=()):
        if "INSERT INTO exceptions" in sql:
            raise sqlite3.OperationalError("SIMULATED: Phase C exceptions insert failure")
        return self._real.execute(sql, params)

    def executescript(self, sql):
        return self._real.executescript(sql)

    def commit(self):
        return self._real.commit()

    def rollback(self):
        return self._real.rollback()

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_run_legacy_import_phase_c_finalization_failure_rolls_back_cleanly():
    """Forces a failure in Phase C AFTER the ingestion_runs UPDATE has already
    executed (but not yet committed), via the thin connection wrapper above -
    not timing. Proves run_legacy_import() rolls back the WHOLE Phase C
    transaction (the UPDATE too, not just the failed exceptions INSERT),
    raises ImportFinalizationError with the original exception chained as
    its cause, leaves the ingestion_runs row at its Phase A state, and
    leaves the real connection with no open transaction and fully usable."""
    real_conn = _fresh_conn()
    _seed_source(real_conn)
    wrapped = _FailingExceptionsInsertConnection(real_conn)

    with _TempLayout() as t:
        bad = t.fake_repo / "kern" / "bad.html"
        bad.write_bytes(b"<html>forces a Phase B failure so Phase C has an exceptions row to write</html>")

        try:
            run_legacy_import(
                wrapped, source_id="TEST_ONLY_SRC_1", county="EXAMPLE_COUNTY",
                records=[
                    {
                        "legacy_path": bad, "source_url_or_identifier": "https://example.invalid/bad",
                        "content_type": "text/html",
                        "observation_fields": (ObservationFieldInput("owner_name", "EXAMPLE OWNER", "NOT_A_REAL_CONFIDENCE_LEVEL"),),
                    },
                ],
                artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
            )
            raise AssertionError("Expected ImportFinalizationError")
        except ImportFinalizationError as e:
            # (a) the expected finalization error, with the original exception chained.
            assert isinstance(e.__cause__, sqlite3.OperationalError)
            assert "SIMULATED" in str(e.__cause__)

        run_id = real_conn.execute(
            "SELECT run_id FROM ingestion_runs WHERE source_id = 'TEST_ONLY_SRC_1'"
        ).fetchone()[0]

        # (b) the ingestion_runs row remains at its Phase A ('attempted') state -
        # the rolled-back Phase C UPDATE must not have changed it at all.
        run_row = real_conn.execute(
            "SELECT status, finished_at, attempted_count, succeeded_count, failed_count "
            "FROM ingestion_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert run_row == ("attempted", None, None, None, None), f"expected untouched Phase A state, got {run_row}"

        # (c) no Phase C exceptions rows persist.
        exc_count = real_conn.execute(
            "SELECT COUNT(*) FROM exceptions WHERE related_entity_id = ?", (run_id,)
        ).fetchone()[0]
        assert exc_count == 0, "the failed exceptions INSERT, and any before it in the same Phase C attempt, must roll back"

        # (d) no open transaction left behind on the real connection.
        assert real_conn.in_transaction is False

        # (e) the real connection still works normally afterward.
        real_conn.execute(
            "INSERT INTO source_registry (source_id, county, county_fips, source_type, name, base_url, access_level, registered_at) VALUES (?,?,?,?,?,?,?,?)",
            ("TEST_ONLY_SRC_2", "TEST_ONLY_COUNTY", "000", "assessor", "TEST_ONLY Source 2", "https://example.invalid", "full", NOW_ISO),
        )
        real_conn.commit()
        assert real_conn.execute(
            "SELECT COUNT(*) FROM source_registry WHERE source_id = 'TEST_ONLY_SRC_2'"
        ).fetchone()[0] == 1
    print("PASS: a Phase C finalization failure (after the ingestion_runs UPDATE) rolls back the whole Phase C transaction, raises ImportFinalizationError chained to its cause, leaves ingestion_runs at its Phase A state, and leaves the connection usable")


# ── Importer boundary: Phase 1 protections still hold; static source-scan proof ──

def test_importer_never_mutates_or_deletes_phase1_evidence_rows():
    conn = _fresh_conn()
    _seed_source(conn)
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        ("TEST_ONLY_RUN_1", "TEST_ONLY_SRC_1", NOW_ISO, "attempted"),
    )
    conn.commit()
    with _TempLayout() as t:
        fixture = t.fake_repo / "kern" / "doc.html"
        fixture.write_bytes(b"<html>immutability check fixture</html>")
        result = import_evidence_record(
            conn, ingestion_run_id="TEST_ONLY_RUN_1", source_id="TEST_ONLY_SRC_1", county="EXAMPLE_COUNTY",
            legacy_path=fixture, source_url_or_identifier="https://example.invalid/doc",
            content_type="text/html", artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )
        try:
            conn.execute("UPDATE raw_evidence SET content_hash = 'x' WHERE evidence_id = ?", (result.evidence_id,))
            raise AssertionError("Expected sqlite3.IntegrityError")
        except sqlite3.IntegrityError:
            pass
        try:
            conn.execute("DELETE FROM raw_evidence WHERE evidence_id = ?", (result.evidence_id,))
            raise AssertionError("Expected sqlite3.IntegrityError")
        except sqlite3.IntegrityError:
            pass
    print("PASS: an importer-written raw_evidence row is exactly as immutable as any other (migration 002's triggers apply)")


def test_importer_source_never_issues_update_or_delete_against_evidence_tables():
    forbidden = [
        "UPDATE raw_evidence", "DELETE FROM raw_evidence",
        "UPDATE observations", "DELETE FROM observations",
        "UPDATE observation_identifiers", "DELETE FROM observation_identifiers",
    ]
    hits = [s for s in forbidden if s in IMPORTER_SOURCE]
    assert not hits, f"importer source contains forbidden statement(s): {hits}"
    print("PASS: legacy_evidence_importer.py's own source contains no UPDATE/DELETE against raw_evidence/observations/observation_identifiers")


def test_importer_never_writes_source_registry():
    forbidden = ["INSERT INTO source_registry", "UPDATE source_registry", "DELETE FROM source_registry"]
    hits = [s for s in forbidden if s in IMPORTER_SOURCE]
    assert not hits, f"importer source contains forbidden statement(s): {hits}"
    assert "SELECT 1 FROM source_registry" in IMPORTER_SOURCE, "expected the read-only existence check to still be present"
    print("PASS: legacy_evidence_importer.py never creates or updates source_registry (read-only lookup only)")


def test_importer_never_creates_or_updates_canonical_property_state():
    forbidden = ["INSERT INTO canonical_property_state", "UPDATE canonical_property_state"]
    hits = [s for s in forbidden if s in IMPORTER_SOURCE]
    assert not hits, f"importer source contains forbidden statement(s): {hits}"
    print("PASS: legacy_evidence_importer.py contains no INSERT/UPDATE against canonical_property_state in this phase")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
