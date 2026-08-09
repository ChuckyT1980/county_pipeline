"""
Tests for property_intelligence_v2/importers/run_del_norte_asrprint_batch.py.

Applies migrations 001-003 (via apply_schema, the same single code path
production code would use) to a fresh temporary in-memory SQLite database
for every test. Never touches a file on disk under the real repository -
legacy files, the fake repository, and artifact roots are all built under
tempfile.TemporaryDirectory() instances. All HTML fixtures are inline and
fully synthetic - no real California data.

Run: python3 property_intelligence_v2/tests/test_run_del_norte_asrprint_batch.py
"""
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "migrations"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "importers"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "extractors"))

from apply_schema import apply_schema  # noqa: E402
from legacy_evidence_importer import (  # noqa: E402
    ImportFinalizationError,
    ImporterConfigError,
    ImporterInputError,
    UnknownSourceError,
)

from run_del_norte_asrprint_batch import (  # noqa: E402
    BatchImporterFailure,
    BatchParserSkip,
    run_del_norte_asrprint_batch,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()

# Fully synthetic - same set already used in the sibling Phase 3B test files.
ALL_22_ROWS = [
    ("Assessor Parcel Number(APN)", "000-000-000-000"),
    ("Assessment Number", "000-000-000-000"),
    ("Tax Rate Area(TRA)", "000000"),
    ("Current Document Number", "2000T0000"),
    ("Current Document  Date", "1/1/2000"),
    ("SitusAddr", "1 EXAMPLE ST EXAMPLE CITY 00000"),
    ("Property Type", "EXAMPLE VACANT LAND"),
    ("Lot Size(Acres)", "1.00"),
    ("Lot Size(SqFt)", "0.00"),
    ("Asmt Description", "EXAMPLE LOT 1, EXAMPLE TRACT"),
    ("Asmt Status", "ACTIVE"),
    ("Land", "$1,000"),
    ("Structural Imprv", "$0"),
    ("Fixtures Real Property", "$0"),
    ("Growing Imprv.", "$0"),
    ("Total land & Improvemnets", "$1,000"),
    ("Fixtures Personal Property", "$0"),
    ("Personal Property", "$0"),
    ("Manufactured Homes", "$0"),
    ("Homeowners Exemption(HOX)", "$0"),
    ("Other Exemptions", "$0"),
    ("Net Assessed Value", "$1,000"),
]


def _build_html(rows, *, include_back_link=True):
    row_html = "\n".join(
        f'<tr><td class="font-weight-bolder">{label}</td><td>{value}</td></tr>'
        for label, value in rows
    )
    back_html = '<a id="Back" href="/mbap/delnorte/asr/AsrMain/000000000000">BACK</a>' if include_back_link else ""
    return f"""
<html lang="en-us">
<head><title>Print | Delnorte  County </title></head>
<body>
{back_html}
<table class="table table-active">
<caption>Property Information</caption>
{row_html}
</table>
</body>
</html>
"""


class _TempLayout:
    """A throwaway artifact_root dir plus a throwaway fake-repo dir with a
    del_norte/raw_evidence/ subfolder. Neither ever touches the real
    repository - matches the pattern already established in the sibling
    Phase 3B test files."""

    def __enter__(self):
        self._tmp = tempfile.mkdtemp(prefix="piv2_asrprint_batch_test_")
        self.tmp = Path(self._tmp)
        self.artifact_root = self.tmp / "artifacts"
        self.fake_repo = self.tmp / "fake_repo"
        (self.fake_repo / "del_norte" / "raw_evidence").mkdir(parents=True)
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self._tmp, ignore_errors=True)


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)  # 001+002+003, the one shared code path
    return conn


def _seed_source(conn: sqlite3.Connection, source_id="TEST_ONLY_SRC_DELNORTE"):
    conn.execute(
        "INSERT INTO source_registry (source_id, county, county_fips, source_type, name, base_url, access_level, registered_at) VALUES (?,?,?,?,?,?,?,?)",
        (source_id, "TEST_ONLY_COUNTY", "000", "assessor", "TEST_ONLY Source", "https://example.invalid", "full", NOW_ISO),
    )
    conn.commit()
    return source_id


def _boundary_tables_untouched(conn: sqlite3.Connection) -> None:
    for table in ("observation_identifiers", "parcels", "parcel_matches", "canonical_property_state"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


# ── All-success multi-record batch ─────────────────────────────────────

def test_all_success_multi_record_batch():
    conn = _fresh_conn()
    source_id = _seed_source(conn)
    with _TempLayout() as t:
        paths = []
        for i in range(3):
            p = t.fake_repo / "del_norte" / "raw_evidence" / f"delnorte_asrprint_ok_{i}.html"
            p.write_text(_build_html(ALL_22_ROWS), encoding="utf-8")
            paths.append(p)

        result = run_del_norte_asrprint_batch(
            conn, source_id=source_id, records=paths,
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )

        assert result.status == "succeeded"
        assert len(result.succeeded) == 3
        assert result.parser_skips == ()
        assert result.importer_failures == ()

        run_row = conn.execute(
            "SELECT status, attempted_count, succeeded_count, failed_count FROM ingestion_runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert run_row == ("succeeded", 3, 3, 0)
        assert conn.execute("SELECT COUNT(*) FROM exceptions WHERE related_entity_id = ?", (result.run_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 3
        _boundary_tables_untouched(conn)
    print("PASS: an all-success multi-record batch produces status='succeeded' and zero exceptions")


# ── Mixed batch: one parser skip, one success ──────────────────────────

def test_mixed_batch_one_parser_skip_one_success():
    conn = _fresh_conn()
    source_id = _seed_source(conn)
    with _TempLayout() as t:
        good = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_good.html"
        good.write_text(_build_html(ALL_22_ROWS), encoding="utf-8")
        bad_rows = [r for r in ALL_22_ROWS if r[0] != "Assessor Parcel Number(APN)"]
        bad = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_bad.html"
        bad.write_text(_build_html(bad_rows), encoding="utf-8")

        result = run_del_norte_asrprint_batch(
            conn, source_id=source_id, records=[good, bad],
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )

        assert result.status == "partial"
        assert len(result.succeeded) == 1
        assert len(result.parser_skips) == 1
        assert result.importer_failures == ()

        run_row = conn.execute(
            "SELECT status, attempted_count, succeeded_count, failed_count FROM ingestion_runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert run_row == ("partial", 2, 1, 1)

        exc_row = conn.execute(
            "SELECT classification, severity, next_action, status, notes FROM exceptions WHERE related_entity_id = ?",
            (result.run_id,),
        ).fetchone()
        assert exc_row[:4] == ("schema_mismatch", "medium", "human_review", "open")
        assert "delnorte_asrprint_bad.html" in exc_row[4]
        assert "AsrPrintExtractionFailure" in exc_row[4]
        _boundary_tables_untouched(conn)
    print("PASS: a mixed batch (one parser skip, one success) produces status='partial' with one correctly-mapped exceptions row")


# ── All parser skips ────────────────────────────────────────────────────

def test_all_parser_skips_batch():
    conn = _fresh_conn()
    source_id = _seed_source(conn)
    with _TempLayout() as t:
        bad_rows = [r for r in ALL_22_ROWS if r[0] != "Assessor Parcel Number(APN)"]
        paths = []
        for i in range(2):
            p = t.fake_repo / "del_norte" / "raw_evidence" / f"delnorte_asrprint_bad_{i}.html"
            p.write_text(_build_html(bad_rows), encoding="utf-8")
            paths.append(p)

        result = run_del_norte_asrprint_batch(
            conn, source_id=source_id, records=paths,
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )

        assert result.status == "failed"
        assert result.succeeded == ()
        assert len(result.parser_skips) == 2
        assert result.importer_failures == ()

        run_row = conn.execute(
            "SELECT status, attempted_count, succeeded_count, failed_count FROM ingestion_runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert run_row == ("failed", 2, 0, 2)
        assert conn.execute("SELECT COUNT(*) FROM exceptions WHERE related_entity_id = ?", (result.run_id,)).fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
        _boundary_tables_untouched(conn)
    print("PASS: an all-parser-skip batch produces status='failed' with one exceptions row per skip")


# ── Importer transaction failure after artifact write; orphan path recorded ──

class _FailingObservationsInsertConnection:
    """Wraps a real sqlite3.Connection. Passes every call straight through,
    except: the first time it sees an INSERT INTO observations statement,
    it raises - simulating a DB-level failure AFTER the artifact has
    already been written (artifact write happens before the transaction
    inside import_evidence_record), so the orphan-artifact path can be
    proven to be tracked correctly."""

    def __init__(self, real_conn: sqlite3.Connection):
        self._real = real_conn
        self._triggered = False

    def execute(self, sql, params=()):
        if not self._triggered and "INSERT INTO observations" in sql:
            self._triggered = True
            raise sqlite3.OperationalError("SIMULATED: observations insert failure")
        return self._real.execute(sql, params)

    def executescript(self, sql):
        return self._real.executescript(sql)

    def commit(self):
        return self._real.commit()

    def rollback(self):
        return self._real.rollback()

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_importer_transaction_failure_records_orphan_artifact():
    real_conn = _fresh_conn()
    source_id = _seed_source(real_conn)
    wrapped = _FailingObservationsInsertConnection(real_conn)
    with _TempLayout() as t:
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_txnfail.html"
        legacy_path.write_text(_build_html(ALL_22_ROWS), encoding="utf-8")

        result = run_del_norte_asrprint_batch(
            wrapped, source_id=source_id, records=[legacy_path],
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )

        assert result.status == "failed"
        assert result.succeeded == ()
        assert result.parser_skips == ()
        assert len(result.importer_failures) == 1
        failure = result.importer_failures[0]
        assert failure.error_type == "ImportTransactionError"
        assert failure.orphan_artifact_path is not None
        assert failure.orphan_artifact_path.exists(), "the orphaned artifact must remain on disk, not be deleted"

        assert real_conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0, \
            "the failed record's transaction must have rolled back with zero partial rows"

        exc_row = real_conn.execute(
            "SELECT classification, severity, next_action, status, notes FROM exceptions WHERE related_entity_id = ?",
            (result.run_id,),
        ).fetchone()
        assert exc_row[:4] == ("unknown", "high", "human_review", "open")
        assert "orphan_artifact_path=" in exc_row[4]
        _boundary_tables_untouched(real_conn)
    print("PASS: an import-transaction failure after artifact write is recorded with its orphan artifact path, and the artifact itself remains on disk")


# ── Deduplicated re-run ──────────────────────────────────────────────────

def test_deduplicated_rerun_counts_as_success_no_duplicate_evidence():
    conn = _fresh_conn()
    source_id = _seed_source(conn)
    with _TempLayout() as t:
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_dedup.html"
        legacy_path.write_text(_build_html(ALL_22_ROWS), encoding="utf-8")

        first = run_del_norte_asrprint_batch(
            conn, source_id=source_id, records=[legacy_path],
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )
        second = run_del_norte_asrprint_batch(
            conn, source_id=source_id, records=[legacy_path],
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )

        assert first.status == "succeeded" and len(first.succeeded) == 1
        assert first.succeeded[0].deduplicated is False

        assert second.status == "succeeded" and len(second.succeeded) == 1
        assert second.succeeded[0].deduplicated is True
        assert second.parser_skips == () and second.importer_failures == ()
        assert second.succeeded[0].evidence_id == first.succeeded[0].evidence_id

        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 1, \
            "a deduplicated re-run must not create a second raw_evidence row"
        assert conn.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0] == 2, \
            "each batch call still creates its own ingestion_runs row, even though no new evidence was written"
        _boundary_tables_untouched(conn)
    print("PASS: a deduplicated re-run counts as success, references the same evidence_id, and creates no duplicate raw_evidence row")


# ── Phase C injected failure after run UPDATE but before exceptions INSERT ──

class _FailingExceptionsInsertConnection:
    """Wraps a real sqlite3.Connection. Passes every call straight through,
    except: the first time it sees an INSERT INTO exceptions statement, it
    raises - simulating a failure during Phase C AFTER the ingestion_runs
    UPDATE has already executed (but not yet committed), without needing
    real concurrency or timing. Matches the equivalent wrapper already
    proven in tests/test_legacy_evidence_importer.py for the generic
    importer's own Phase C."""

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


def test_phase_c_finalization_failure_rolls_back_cleanly():
    real_conn = _fresh_conn()
    source_id = _seed_source(real_conn)
    wrapped = _FailingExceptionsInsertConnection(real_conn)
    with _TempLayout() as t:
        bad_rows = [r for r in ALL_22_ROWS if r[0] != "Assessor Parcel Number(APN)"]
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_phasec.html"
        legacy_path.write_text(_build_html(bad_rows), encoding="utf-8")

        try:
            run_del_norte_asrprint_batch(
                wrapped, source_id=source_id, records=[legacy_path],
                artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
            )
            raise AssertionError("Expected ImportFinalizationError")
        except ImportFinalizationError as e:
            assert isinstance(e.__cause__, sqlite3.OperationalError)
            assert "SIMULATED" in str(e.__cause__)

        run_id = real_conn.execute(
            "SELECT run_id FROM ingestion_runs WHERE source_id = ?", (source_id,)
        ).fetchone()[0]
        run_row = real_conn.execute(
            "SELECT status, finished_at, attempted_count, succeeded_count, failed_count FROM ingestion_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert run_row == ("attempted", None, None, None, None), \
            f"expected the rolled-back UPDATE to leave the run at its Phase A state, got {run_row}"

        assert real_conn.execute("SELECT COUNT(*) FROM exceptions WHERE related_entity_id = ?", (run_id,)).fetchone()[0] == 0
        assert real_conn.in_transaction is False, "no dangling transaction may remain on the real connection"

        # The real connection must still work normally afterward.
        real_conn.execute(
            "INSERT INTO source_registry (source_id, county, county_fips, source_type, name, base_url, access_level, registered_at) VALUES (?,?,?,?,?,?,?,?)",
            ("TEST_ONLY_SRC_2", "TEST_ONLY_COUNTY", "000", "assessor", "TEST_ONLY Source 2", "https://example.invalid", "full", NOW_ISO),
        )
        real_conn.commit()
        assert real_conn.execute("SELECT COUNT(*) FROM source_registry WHERE source_id = 'TEST_ONLY_SRC_2'").fetchone()[0] == 1
    print("PASS: a Phase C failure (after the run UPDATE, before the exceptions insert) rolls back the whole Phase C transaction, leaves the run at its Phase A state, creates zero exceptions rows, and leaves no dangling transaction")


# ── Outside-repository / denied nested paths ─────────────────────────────

def test_outside_repository_path_is_importer_failure_with_no_evidence():
    conn = _fresh_conn()
    source_id = _seed_source(conn)
    with _TempLayout() as t:
        outside_dir = t.tmp / "outside_the_fake_repo_dir"  # directory, not a readable file - see del_norte_asrprint_pipeline's own test suite for why
        outside_dir.mkdir()

        result = run_del_norte_asrprint_batch(
            conn, source_id=source_id, records=[outside_dir],
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )

        assert result.status == "failed"
        assert len(result.importer_failures) == 1
        assert result.importer_failures[0].error_type == "ImporterInputError"
        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
        assert not any(t.artifact_root.rglob("*")), "no artifact file may exist when path validation rejects the input"
        _boundary_tables_untouched(conn)
    print("PASS: a legacy_path outside the fake repository is recorded as an ImporterInputError importer failure, with zero raw_evidence rows and zero artifacts")


def test_denied_nested_path_is_importer_failure_with_no_evidence():
    conn = _fresh_conn()
    source_id = _seed_source(conn)
    with _TempLayout() as t:
        paths = []
        for denied_component in ("monitor_runs", "output"):
            denied_dir = t.fake_repo / "del_norte" / denied_component
            denied_dir.mkdir(parents=True, exist_ok=True)
            paths.append(denied_dir)

        result = run_del_norte_asrprint_batch(
            conn, source_id=source_id, records=paths,
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )

        assert result.status == "failed"
        assert len(result.importer_failures) == 2
        assert all(f.error_type == "ImporterInputError" for f in result.importer_failures)
        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
        assert not any(t.artifact_root.rglob("*")), "no artifact file may exist when path validation rejects the input"
        _boundary_tables_untouched(conn)
    print("PASS: legacy_paths under del_norte/monitor_runs/ and del_norte/output/ are each recorded as ImporterInputError importer failures, with zero raw_evidence rows and zero artifacts")


# ── Phase A preflight failures ────────────────────────────────────────────

def test_invalid_artifact_root_fails_before_phase_a_zero_ingestion_runs():
    conn = _fresh_conn()
    source_id = _seed_source(conn)
    with _TempLayout() as t:
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_unused.html"
        legacy_path.write_text(_build_html(ALL_22_ROWS), encoding="utf-8")

        try:
            run_del_norte_asrprint_batch(
                conn, source_id=source_id, records=[legacy_path],
                artifact_root=Path("relative/not/absolute"), repo_root=t.fake_repo, now=NOW,
            )
            raise AssertionError("Expected ImporterConfigError")
        except ImporterConfigError:
            pass

        assert conn.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
    print("PASS: an invalid artifact_root raises ImporterConfigError before Phase A creates any ingestion_runs row")


def test_unknown_source_fails_before_phase_a_zero_ingestion_runs():
    conn = _fresh_conn()
    # Deliberately do NOT seed a source_registry row.
    with _TempLayout() as t:
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_unused.html"
        legacy_path.write_text(_build_html(ALL_22_ROWS), encoding="utf-8")

        try:
            run_del_norte_asrprint_batch(
                conn, source_id="TEST_ONLY_SRC_NEVER_REGISTERED", records=[legacy_path],
                artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
            )
            raise AssertionError("Expected UnknownSourceError")
        except UnknownSourceError:
            pass

        assert conn.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM exceptions").fetchone()[0] == 0
    print("PASS: an unknown source_id raises UnknownSourceError before Phase A creates any ingestion_runs row, and no exceptions row is created either")


# ── Cross-cutting: successful-with-warnings creates no exceptions row ────

def test_successful_import_with_warnings_creates_no_exceptions_row():
    conn = _fresh_conn()
    source_id = _seed_source(conn)
    with _TempLayout() as t:
        # Omit an optional field and add an unrecognized label - both are
        # warning-worthy but still a successful parse and import.
        rows = [r for r in ALL_22_ROWS if r[0] != "Structural Imprv"]
        rows = rows + [("Not A Known Label", "some value")]
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_warnings.html"
        legacy_path.write_text(_build_html(rows), encoding="utf-8")

        result = run_del_norte_asrprint_batch(
            conn, source_id=source_id, records=[legacy_path],
            artifact_root=t.artifact_root, repo_root=t.fake_repo, now=NOW,
        )

        assert result.status == "succeeded"
        assert len(result.succeeded) == 1
        assert result.parser_skips == () and result.importer_failures == ()
        assert conn.execute("SELECT COUNT(*) FROM exceptions WHERE related_entity_id = ?", (result.run_id,)).fetchone()[0] == 0
        _boundary_tables_untouched(conn)
    print("PASS: a successful import with parser warnings (missing optional field, unrecognized label) creates no exceptions row")


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
