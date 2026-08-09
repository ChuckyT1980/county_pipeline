"""
Tests for property_intelligence_v2/extractors/del_norte_asrprint_pipeline.py.

Applies migrations 001-003 (via apply_schema, the same single code path
production code would use) to a fresh temporary in-memory SQLite database
for every test. Never touches a file on disk under the real repository -
legacy files and artifact roots are built under tempfile.TemporaryDirectory()
instances, structured as a FAKE repository with its own del_norte/ folder,
never del_norte/'s real files. All HTML fixtures are inline and fully
synthetic - no real California data.

Run: python3 property_intelligence_v2/tests/test_del_norte_asrprint_pipeline.py
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
from legacy_evidence_importer import ImportResult, ImporterInputError  # noqa: E402

from del_norte_asrprint_pipeline import (  # noqa: E402
    PipelineSkipped,
    import_asrprint_file,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()

# Fully synthetic - see test_del_norte_asrprint_extractor.py's own fixture
# for the same set, reused here for the happy-path pipeline test.
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
    repository - matches the pattern already established in
    tests/test_legacy_evidence_importer.py."""

    def __enter__(self):
        self._tmp = tempfile.mkdtemp(prefix="piv2_asrprint_pipeline_test_")
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


def _seed_source_and_run(conn: sqlite3.Connection, source_id="TEST_ONLY_SRC_DELNORTE", run_id="TEST_ONLY_RUN_DELNORTE"):
    conn.execute(
        "INSERT INTO source_registry (source_id, county, county_fips, source_type, name, base_url, access_level, registered_at) VALUES (?,?,?,?,?,?,?,?)",
        (source_id, "TEST_ONLY_COUNTY", "000", "assessor", "TEST_ONLY Source", "https://example.invalid", "full", NOW_ISO),
    )
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        (run_id, source_id, NOW_ISO, "attempted"),
    )
    conn.commit()
    return source_id, run_id


def test_successful_extraction_produces_raw_evidence_disposition_and_observations_only():
    conn = _fresh_conn()
    source_id, run_id = _seed_source_and_run(conn)
    with _TempLayout() as t:
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_000000000000.html"
        legacy_path.write_text(_build_html(ALL_22_ROWS), encoding="utf-8")

        result = import_asrprint_file(
            conn,
            ingestion_run_id=run_id,
            source_id=source_id,
            legacy_path=legacy_path,
            artifact_root=t.artifact_root,
            repo_root=t.fake_repo,
            now=NOW,
        )

        assert isinstance(result, ImportResult), result
        assert result.artifact_written is True
        assert result.artifact_path.exists()
        assert result.artifact_path.is_relative_to(t.artifact_root)

        ev_row = conn.execute(
            "SELECT content_type, source_url_or_identifier FROM raw_evidence WHERE evidence_id = ?",
            (result.evidence_id,),
        ).fetchone()
        assert ev_row == ("text/html", "del_norte/raw_evidence/delnorte_asrprint_000000000000.html")

        disp = conn.execute(
            "SELECT current_disposition FROM v_evidence_current_disposition WHERE evidence_id = ?",
            (result.evidence_id,),
        ).fetchone()[0]
        assert disp == "ACTIVE"

        obs_rows = conn.execute(
            "SELECT field_name, county, confidence FROM observations WHERE evidence_id = ?", (result.evidence_id,)
        ).fetchall()
        assert len(obs_rows) == 23, f"expected 22 known fields + related link, got {len(obs_rows)}"
        assert all(county == "Del Norte" for _, county, _ in obs_rows)
        assert all(confidence == "carried_forward" for _, _, confidence in obs_rows), obs_rows
        assert not any(confidence == "confirmed" for _, _, confidence in obs_rows), \
            "archived local HTML must never persist as confidence='confirmed'"

        # Boundary check: nothing else was written for this record.
        assert conn.execute("SELECT COUNT(*) FROM observation_identifiers").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM exceptions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM parcels").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM canonical_property_state").fetchone()[0] == 0
    print("PASS: a successful extraction/import produces exactly raw_evidence + ACTIVE disposition + observations - nothing else")


def test_parser_failure_produces_zero_db_writes_zero_artifacts_and_skips_the_importer():
    conn = _fresh_conn()
    source_id, run_id = _seed_source_and_run(conn)
    with _TempLayout() as t:
        rows_missing_apn = [r for r in ALL_22_ROWS if r[0] != "Assessor Parcel Number(APN)"]
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_bad.html"
        legacy_path.write_text(_build_html(rows_missing_apn), encoding="utf-8")

        result = import_asrprint_file(
            conn,
            ingestion_run_id=run_id,
            source_id=source_id,
            legacy_path=legacy_path,
            artifact_root=t.artifact_root,
            repo_root=t.fake_repo,
            now=NOW,
        )

        assert isinstance(result, PipelineSkipped), result
        assert result.failure.classification == "schema_mismatch"
        assert result.legacy_path == legacy_path.resolve(), \
            "PipelineSkipped carries the validated (resolved) path, per Fix 2"

        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM evidence_disposition").fetchone()[0] == 0
        assert not any(t.artifact_root.rglob("*")), "no artifact file may exist when the parser fails"
    print("PASS: a parser failure (missing APN) produces zero raw_evidence rows, zero artifacts, and import_evidence_record is never invoked")


def test_warnings_do_not_create_exceptions_rows():
    conn = _fresh_conn()
    source_id, run_id = _seed_source_and_run(conn)
    with _TempLayout() as t:
        # Omit an optional field (warning-worthy) and add an unrecognized
        # label (also warning-worthy) - both are still a successful parse.
        rows = [r for r in ALL_22_ROWS if r[0] != "Structural Imprv"]
        rows = rows + [("Not A Known Label", "some value")]
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_warnings.html"
        legacy_path.write_text(_build_html(rows), encoding="utf-8")

        result = import_asrprint_file(
            conn,
            ingestion_run_id=run_id,
            source_id=source_id,
            legacy_path=legacy_path,
            artifact_root=t.artifact_root,
            repo_root=t.fake_repo,
            now=NOW,
        )

        assert isinstance(result, ImportResult), result
        assert conn.execute("SELECT COUNT(*) FROM exceptions").fetchone()[0] == 0, \
            "warnings on an otherwise-successful import must never create an exceptions row"
        obs_field_names = {
            r[0] for r in conn.execute(
                "SELECT field_name FROM observations WHERE evidence_id = ?", (result.evidence_id,)
            ).fetchall()
        }
        assert "roll_value_structural_improvements" not in obs_field_names
        assert not any("not a known label" in fn.lower() or "unknown" in fn.lower() for fn in obs_field_names)
    print("PASS: warnings (missing optional field, unrecognized label) accompany a successful import without creating any exceptions row")


def test_source_locator_is_repository_relative_legacy_path_not_a_url():
    conn = _fresh_conn()
    source_id, run_id = _seed_source_and_run(conn)
    with _TempLayout() as t:
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_locator_check.html"
        legacy_path.write_text(_build_html(ALL_22_ROWS), encoding="utf-8")

        result = import_asrprint_file(
            conn,
            ingestion_run_id=run_id,
            source_id=source_id,
            legacy_path=legacy_path,
            artifact_root=t.artifact_root,
            repo_root=t.fake_repo,
            now=NOW,
        )

        assert isinstance(result, ImportResult), result
        locator = conn.execute(
            "SELECT source_url_or_identifier FROM raw_evidence WHERE evidence_id = ?", (result.evidence_id,)
        ).fetchone()[0]
        assert locator == "del_norte/raw_evidence/delnorte_asrprint_locator_check.html"
        assert not locator.startswith("http"), "must never be a reconstructed live URL"
        assert "/mbap/" not in locator, "must never be the observed AsrMain link, only the legacy file's own path"

        # The AsrMain link IS still captured, but as ordinary page content,
        # not as the source locator.
        related_link_value = conn.execute(
            "SELECT field_value FROM observations WHERE evidence_id = ? AND field_name = 'assessor_portal_related_link'",
            (result.evidence_id,),
        ).fetchone()[0]
        assert related_link_value == "/mbap/delnorte/asr/AsrMain/000000000000"
    print("PASS: source_url_or_identifier is the repository-relative legacy path; the AsrMain link is captured only as ordinary page content")


def test_outside_repository_path_raises_before_any_read_or_import():
    """Fix 2, case A: a legacy_path outside the fake repository entirely
    must raise ImporterInputError from validate_legacy_input_path() BEFORE
    any read is attempted.

    Why a DIRECTORY, not a readable .html file: validate_legacy_input_path()
    is pure path-string validation - it doesn't require the target to
    exist and doesn't touch the filesystem - so it rejects legacy_path on
    a real file and on an empty directory identically. But a readable file
    does NOT prove validate-before-read ordering: under the old, buggy
    read-first ordering (the exact bug Fix 2 corrected), legacy_path.read_text()
    would succeed on a real file, parsing would proceed, and
    import_evidence_record()'s own LATER validate_legacy_input_path() call
    would still eventually raise the same ImporterInputError - just too
    late, after the unvalidated read already happened, with nothing in
    this test able to tell the two orderings apart. A directory makes the
    ordering itself observable: legacy_path.read_text() on a directory
    raises IsADirectoryError, a DIFFERENT exception type, not
    ImporterInputError. So under the old read-first ordering this test
    fails outright (wrong exception type reaches the caller); it passes
    only under the corrected validate-first ordering, where read_text() on
    this path is never reached at all."""
    conn = _fresh_conn()
    source_id, run_id = _seed_source_and_run(conn)
    with _TempLayout() as t:
        outside_dir = t.tmp / "outside_the_fake_repo_dir"  # a sibling of fake_repo, not inside it - a directory, not a file
        outside_dir.mkdir()

        try:
            import_asrprint_file(
                conn,
                ingestion_run_id=run_id,
                source_id=source_id,
                legacy_path=outside_dir,
                artifact_root=t.artifact_root,
                repo_root=t.fake_repo,
                now=NOW,
            )
            raise AssertionError("Expected ImporterInputError")
        except ImporterInputError:
            pass
        except IsADirectoryError:
            raise AssertionError(
                "Got IsADirectoryError instead of ImporterInputError - legacy_path was read (via "
                "read_text()) before validate_legacy_input_path() rejected it, meaning the "
                "read-before-validate ordering bug Fix 2 corrected has regressed."
            )

        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
        assert not any(t.artifact_root.rglob("*")), "no artifact file may exist when path validation rejects the input"
    print("PASS: a legacy_path outside the fake repository (a directory, not a readable file - so an accidental pre-validation read would raise a distinguishable IsADirectoryError) raises ImporterInputError before any read is attempted, with zero raw_evidence rows and zero artifacts")


def test_denied_nested_path_raises_before_any_read_or_import():
    """Fix 2, case B: a legacy_path under a denied component
    (del_norte/monitor_runs/ or del_norte/output/), even though it is
    nested under the allowed del_norte/ root, must raise
    ImporterInputError before any read is attempted.

    Uses the denied DIRECTORY itself as legacy_path, not a readable file
    beneath it - same reasoning as
    test_outside_repository_path_raises_before_any_read_or_import above: a
    readable file would let an accidental read-before-validate ordering
    eventually reach import_evidence_record()'s own later validation and
    still raise ImporterInputError, just too late to prove anything about
    ordering. A directory makes an accidental pre-validation read
    deterministically observable instead, via IsADirectoryError - a
    different, distinguishable exception type - if the ordering bug ever
    regresses."""
    conn = _fresh_conn()
    source_id, run_id = _seed_source_and_run(conn)
    with _TempLayout() as t:
        for denied_component in ("monitor_runs", "output"):
            denied_dir = t.fake_repo / "del_norte" / denied_component
            denied_dir.mkdir(parents=True, exist_ok=True)

            try:
                import_asrprint_file(
                    conn,
                    ingestion_run_id=run_id,
                    source_id=source_id,
                    legacy_path=denied_dir,
                    artifact_root=t.artifact_root,
                    repo_root=t.fake_repo,
                    now=NOW,
                )
                raise AssertionError(f"Expected ImporterInputError for a path under {denied_component!r}")
            except ImporterInputError:
                pass
            except IsADirectoryError:
                raise AssertionError(
                    f"Got IsADirectoryError instead of ImporterInputError for {denied_component!r} - "
                    "legacy_path was read (via read_text()) before validate_legacy_input_path() "
                    "rejected it, meaning the read-before-validate ordering bug Fix 2 corrected has "
                    "regressed."
                )

        assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
        assert not any(t.artifact_root.rglob("*")), "no artifact file may exist when path validation rejects the input"
    print("PASS: legacy_path under del_norte/monitor_runs/ or del_norte/output/ (the denied directory itself, not a readable file - so an accidental pre-validation read would raise a distinguishable IsADirectoryError) raises ImporterInputError before any read is attempted, with zero raw_evidence rows and zero artifacts")


def test_persisted_observations_are_carried_forward_never_confirmed():
    """Part C's pipeline-level check: run the synthetic pipeline path (with
    and without the related link) and assert every PERSISTED observations
    row uses confidence='carried_forward', never 'confirmed' - the same
    guarantee test_del_norte_asrprint_extractor.py proves at the in-memory
    dataclass level, proven again here at the actual database level."""
    conn = _fresh_conn()
    source_id, run_id = _seed_source_and_run(conn)
    with _TempLayout() as t:
        with_link_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_conf_with_link.html"
        with_link_path.write_text(_build_html(ALL_22_ROWS, include_back_link=True), encoding="utf-8")
        without_link_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_conf_without_link.html"
        without_link_path.write_text(_build_html(ALL_22_ROWS, include_back_link=False), encoding="utf-8")

        for legacy_path in (with_link_path, without_link_path):
            result = import_asrprint_file(
                conn,
                ingestion_run_id=run_id,
                source_id=source_id,
                legacy_path=legacy_path,
                artifact_root=t.artifact_root,
                repo_root=t.fake_repo,
                now=NOW,
            )
            assert isinstance(result, ImportResult), result
            confidences = [
                r[0] for r in conn.execute(
                    "SELECT confidence FROM observations WHERE evidence_id = ?", (result.evidence_id,)
                ).fetchall()
            ]
            assert confidences, "expected at least one persisted observation"
            assert all(c == "carried_forward" for c in confidences), confidences
            assert not any(c == "confirmed" for c in confidences), confidences
    print("PASS: persisted observations from the synthetic pipeline path are always confidence='carried_forward', never 'confirmed', with and without the related link")


def test_identifier_candidates_from_parser_are_never_persisted_by_the_driver():
    conn = _fresh_conn()
    source_id, run_id = _seed_source_and_run(conn)
    with _TempLayout() as t:
        legacy_path = t.fake_repo / "del_norte" / "raw_evidence" / "delnorte_asrprint_identifiers.html"
        legacy_path.write_text(_build_html(ALL_22_ROWS), encoding="utf-8")

        result = import_asrprint_file(
            conn,
            ingestion_run_id=run_id,
            source_id=source_id,
            legacy_path=legacy_path,
            artifact_root=t.artifact_root,
            repo_root=t.fake_repo,
            now=NOW,
        )

        assert isinstance(result, ImportResult), result
        assert conn.execute("SELECT COUNT(*) FROM observation_identifiers").fetchone()[0] == 0
    print("PASS: the parser's in-memory identifier candidates are never written to observation_identifiers by the driver")


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
