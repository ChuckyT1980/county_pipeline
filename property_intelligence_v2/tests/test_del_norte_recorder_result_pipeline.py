"""
Tests for property_intelligence_v2/extractors/del_norte_recorder_result_pipeline.py.

No real HTTP request anywhere in this file - the live client is always
called with an injected fake opener (never a real socket) and a no-op
sleeper. Uses a fresh temporary in-memory SQLite database (via apply_schema,
the same single code path production code uses) and a throwaway external
artifact_root under tempfile.mkdtemp() per test - never the real repository
or a real trial database.

TEST_ONLY_ rule (see legacy_evidence_importer.py's reject_test_only()):
gate-FAILURE fixtures (client blocked/error, parser failure, zero/multiple
results, mismatch) are free to use TEST_ONLY_ HTML/values since nothing
ever reaches the importer in those cases. Gate-PASSING (success) fixtures
must avoid "TEST_ONLY_" anywhere in the recorder-result HTML, since that
HTML becomes raw_content and would otherwise trip the importer's own
TEST_ONLY_ rejection before persisting - success fixtures use EXAMPLE_*
placeholder party names and doc-number-shaped values instead.
source_id/ingestion_run_id keep the normal TEST_ONLY_ prefix throughout
(not covered by reject_test_only - see test_legacy_evidence_importer.py's
own module docstring for the same established exception).

Run: python3 property_intelligence_v2/tests/test_del_norte_recorder_result_pipeline.py
"""
import shutil
import sqlite3
import sys
import tempfile
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "migrations"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "importers"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "extractors"))

from apply_schema import apply_schema  # noqa: E402
from legacy_evidence_importer import ImportResult  # noqa: E402
from del_norte_recorder_live_client import (  # noqa: E402
    BASE_URL,
    ADVANCED_SEARCH_ID,
    apply_doc_transform,
)
from del_norte_recorder_result_pipeline import (  # noqa: E402
    RecorderPipelineNotImported,
    import_recorder_document_number_result,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()

DOC_NUMBER = "2000R0000"  # assessor-form input; no TEST_ONLY_ substring
TRANSFORMED = apply_doc_transform(DOC_NUMBER)

DISCLAIMER_URL = f"{BASE_URL}/web/user/disclaimer"
SEARCH_FORM_URL = f"{BASE_URL}/web/search/{ADVANCED_SEARCH_ID}"
RESULTS_URL_PREFIX = f"{BASE_URL}/web/searchResults/{ADVANCED_SEARCH_ID}"


# ── DB/artifact-root scaffolding (mirrors test_legacy_evidence_importer.py's
# own conventions - redefined locally, not imported, per this repository's
# established one-fault-injection-class-per-file convention) ──────────────

def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    return conn


def _seed_source(conn: sqlite3.Connection, source_id: str = "TEST_ONLY_RECORDER_SRC") -> None:
    conn.execute(
        "INSERT INTO source_registry (source_id, county, county_fips, source_type, name, base_url, access_level, registered_at) VALUES (?,?,?,?,?,?,?,?)",
        (source_id, "Del Norte", "015", "recorder", "TEST_ONLY Recorder Source", "https://example.invalid", "unknown", NOW_ISO),
    )
    conn.commit()


class _TempArtifactRoot:
    def __enter__(self):
        self._tmp = tempfile.mkdtemp(prefix="piv2_recorder_pipeline_test_")
        self.path = Path(self._tmp) / "artifacts"
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self._tmp, ignore_errors=True)


# ── fake HTTP layer (redefined locally, mirrors
# test_del_norte_recorder_live_client.py's own fixtures) ──────────────────

class _FakeResponse:
    def __init__(self, body: bytes = b"", status: int = 200, url: str | None = None):
        self._body = body
        self.status = status
        self._url = url

    def read(self) -> bytes:
        return self._body

    def geturl(self) -> str:
        return self._url


class _FakeOpener:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append({"method": request.get_method(), "url": request.full_url})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _no_sleep(_seconds):
    pass


# ── synthetic recorder-results HTML builders (mirrors
# test_del_norte_recorder_result.py's own builders - redefined locally) ───

def _build_row_html(
    *,
    document_number=TRANSFORMED,
    instrument_type="EXAMPLE_TYPE",
    recording_date="01/01/1900",
    grantors=("EXAMPLE_GRANTOR_1",),
    grantees=("EXAMPLE_GRANTEE_1",),
    detail_href="/web/document/EXAMPLE_DOC000S000",
    apn=None,
    book_page=None,
):
    header = f"{document_number} • {instrument_type}"
    cols = [f'<div class="searchResultThreeColumn"><li>Recording Date</li><li>{recording_date}</li></div>']
    names_html = "".join(f"<li>{n}</li>" for n in grantors)
    cols.append(f'<div class="searchResultThreeColumn"><li>Grantor ({len(grantors)})</li>{names_html}</div>')
    names_html = "".join(f"<li>{n}</li>" for n in grantees)
    cols.append(f'<div class="searchResultThreeColumn"><li>Grantee</li>{names_html}</div>')
    if apn is not None:
        value_html = f"<li>{apn}</li>" if apn else ""
        cols.append(f'<div class="searchResultThreeColumn"><li>APN</li>{value_html}</div>')
    if book_page is not None:
        value_html = f"<li>{book_page}</li>" if book_page else ""
        cols.append(f'<div class="searchResultThreeColumn"><li>Book/Page</li>{value_html}</div>')
    detail_link = f'<a href="{detail_href}">View</a>' if detail_href else ""
    return f'<li class="ss-search-row"><h1>{header}</h1>{"".join(cols)}{detail_link}</li>'


def _build_results_page_html(rows_html):
    return f"<html><body><ul>{''.join(rows_html)}</ul></body></html>"


def _happy_path_responses(results_body: bytes):
    return [
        _FakeResponse(b"<html>disclaimer, clean</html>", 200, DISCLAIMER_URL),
        _FakeResponse(b"", 200, DISCLAIMER_URL),
        _FakeResponse(b"<html>search form, clean</html>", 200, SEARCH_FORM_URL),
        _FakeResponse(b"", 200, f"{BASE_URL}/web/searchPost/{ADVANCED_SEARCH_ID}"),
        _FakeResponse(results_body, 200, f"{RESULTS_URL_PREFIX}?page=1&_=123"),
    ]


def _run_pipeline(conn, artifact_root, responses, *, source_id="TEST_ONLY_RECORDER_SRC"):
    opener = _FakeOpener(responses)
    result = import_recorder_document_number_result(
        conn,
        ingestion_run_id="TEST_ONLY_RUN_1",
        source_id=source_id,
        document_number_assessor_form=DOC_NUMBER,
        artifact_root=artifact_root,
        user_agent="TEST_ONLY_PropertyIntelligenceResearch/0.1",
        now=NOW,
        opener_factory=lambda: opener,
        sleep=_no_sleep,
    )
    return result, opener


def _assert_zero_writes(conn, artifact_root):
    assert conn.execute("SELECT COUNT(*) FROM raw_evidence").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    assert not artifact_root.exists() or not any(artifact_root.rglob("*")), "no artifact should be written"


def _seed_run(conn):
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        ("TEST_ONLY_RUN_1", "TEST_ONLY_RECORDER_SRC", NOW_ISO, "attempted"),
    )
    conn.commit()


# ── tests ──────────────────────────────────────────────────────────────

def test_clean_one_row_import_succeeds_byte_for_byte_and_confirmed():
    conn = _fresh_conn()
    _seed_source(conn)
    _seed_run(conn)
    with _TempArtifactRoot() as t:
        results_body = _build_results_page_html([_build_row_html(
            grantors=("EXAMPLE_GRANTOR_1", "EXAMPLE_GRANTOR_2"),
            grantees=("EXAMPLE_GRANTEE_1",),
        )]).encode("utf-8")

        result, opener = _run_pipeline(conn, t.path, _happy_path_responses(results_body))

        assert isinstance(result, ImportResult), result
        assert result.deduplicated is False
        assert result.artifact_written is True
        assert result.artifact_path.read_bytes() == results_body, "persisted artifact must be byte-for-byte the live response received"
        assert result.artifact_path.is_relative_to(t.path)
        assert len(opener.calls) == 5, "no request beyond the 5-step lookup flow - in particular, no detail-link fetch"

        obs = {
            r[0]: (r[1], r[2])
            for r in conn.execute(
                "SELECT field_name, field_value, confidence FROM observations WHERE evidence_id = ?",
                (result.evidence_id,),
            ).fetchall()
        }
        assert obs["recorder_document_number"] == (TRANSFORMED, "confirmed")
        assert obs["recorder_recording_date"] == ("01/01/1900", "confirmed")
        assert obs["recorder_instrument_type"] == ("EXAMPLE_TYPE", "confirmed")
        assert obs["recorder_grantor_name_1"] == ("EXAMPLE_GRANTOR_1", "confirmed")
        assert obs["recorder_grantor_name_2"] == ("EXAMPLE_GRANTOR_2", "confirmed")
        assert obs["recorder_grantee_name_1"] == ("EXAMPLE_GRANTEE_1", "confirmed")
        assert obs["recorder_detail_link_path"] == ("/web/document/EXAMPLE_DOC000S000", "confirmed")
        assert "recorder_apn" not in obs, "no APN observation when the parser never reported the field present"
        assert "recorder_book_page" not in obs, "no book/page observation when the parser never reported the field present"

        ev_row = conn.execute(
            "SELECT source_url_or_identifier, content_type FROM raw_evidence WHERE evidence_id = ?",
            (result.evidence_id,),
        ).fetchone()
        assert ev_row == (f"recorder:{ADVANCED_SEARCH_ID}:document_number={TRANSFORMED}", "text/html")

        for table in ("observation_identifiers", "parcels", "parcel_matches", "canonical_property_state", "exceptions"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    print("PASS: a clean one-row match imports byte-for-byte identical raw evidence, correct ordinal party observations, confidence='confirmed' throughout, opaque unfetched detail-link persistence, no APN/book-page when absent, and every boundary table stays empty")


def test_duplicate_party_blocks_preserve_order_and_repeats_through_full_pipeline():
    conn = _fresh_conn()
    _seed_source(conn)
    _seed_run(conn)
    with _TempArtifactRoot() as t:
        row_html = (
            f'<li class="ss-search-row"><h1>{TRANSFORMED} • EXAMPLE_TYPE</h1>'
            '<div class="searchResultThreeColumn"><li>Recording Date</li><li>01/01/1900</li></div>'
            '<div class="searchResultThreeColumn"><li>Grantor (2)</li><li>EXAMPLE_GRANTOR_A</li><li>EXAMPLE_GRANTOR_A</li></div>'
            '<div class="searchResultThreeColumn"><li>Grantor (1)</li><li>EXAMPLE_GRANTOR_B</li></div>'
            '<div class="searchResultThreeColumn"><li>Grantee</li><li>EXAMPLE_GRANTEE_A</li></div>'
            '<a href="/web/document/EXAMPLE_DOC000S000">View</a></li>'
        )
        results_body = _build_results_page_html([row_html]).encode("utf-8")

        result, _ = _run_pipeline(conn, t.path, _happy_path_responses(results_body))
        assert isinstance(result, ImportResult), result

        obs = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT field_name, field_value FROM observations WHERE evidence_id = ?", (result.evidence_id,),
            ).fetchall()
        }
        assert obs["recorder_grantor_name_1"] == "EXAMPLE_GRANTOR_A"
        assert obs["recorder_grantor_name_2"] == "EXAMPLE_GRANTOR_A"
        assert obs["recorder_grantor_name_3"] == "EXAMPLE_GRANTOR_B"
        assert "recorder_grantor_name_4" not in obs
    print("PASS: duplicate Grantor blocks (including an exact repeated name) are persisted as ordered recorder_grantor_name_1..N observations, exactly matching the parser's own preserved source order")


def test_apn_and_book_page_persisted_only_when_present_and_nonblank():
    conn = _fresh_conn()
    _seed_source(conn)
    _seed_run(conn)
    with _TempArtifactRoot() as t:
        results_body = _build_results_page_html([_build_row_html(
            apn="000-000-000-000", book_page="",  # APN populated, book/page present-but-blank
        )]).encode("utf-8")

        result, _ = _run_pipeline(conn, t.path, _happy_path_responses(results_body))
        assert isinstance(result, ImportResult), result

        obs = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT field_name, field_value FROM observations WHERE evidence_id = ?", (result.evidence_id,),
            ).fetchall()
        }
        assert obs["recorder_apn"] == "000-000-000-000"
        assert "recorder_book_page" not in obs, "present-but-blank book/page must not produce an observation"
    print("PASS: a populated APN is persisted; a present-but-blank book/page is correctly omitted")


def test_client_blocked_produces_zero_writes():
    conn = _fresh_conn()
    _seed_source(conn)
    _seed_run(conn)
    with _TempArtifactRoot() as t:
        responses = [_FakeResponse(b"<html>please solve this grecaptcha</html>", 200, DISCLAIMER_URL)]
        result, opener = _run_pipeline(conn, t.path, responses)
        assert isinstance(result, RecorderPipelineNotImported), result
        assert result.reason == "client_blocked:captcha_detected"
        assert len(opener.calls) == 1
        _assert_zero_writes(conn, t.path)
    print("PASS: a client-blocked lookup (CAPTCHA) produces RecorderPipelineNotImported and zero DB/artifact writes")


def test_client_error_produces_zero_writes():
    conn = _fresh_conn()
    _seed_source(conn)
    _seed_run(conn)
    with _TempArtifactRoot() as t:
        responses = [urllib.error.URLError("TEST_ONLY simulated failure")]
        result, _ = _run_pipeline(conn, t.path, responses)
        assert isinstance(result, RecorderPipelineNotImported), result
        assert result.reason == "client_error:transport_failure"
        _assert_zero_writes(conn, t.path)
    print("PASS: a client transport error produces RecorderPipelineNotImported and zero DB/artifact writes")


def test_parser_failure_produces_zero_writes():
    conn = _fresh_conn()
    _seed_source(conn)
    _seed_run(conn)
    with _TempArtifactRoot() as t:
        unrecognized_body = b"<html><body>TEST_ONLY_ totally unrecognized page shape</body></html>"
        result, _ = _run_pipeline(conn, t.path, _happy_path_responses(unrecognized_body))
        assert isinstance(result, RecorderPipelineNotImported), result
        assert result.reason == "parser_failure"
        _assert_zero_writes(conn, t.path)
    print("PASS: an unrecognized page shape produces RecorderPipelineNotImported(reason='parser_failure') and zero DB/artifact writes")


def test_zero_results_produces_zero_writes():
    conn = _fresh_conn()
    _seed_source(conn)
    _seed_run(conn)
    with _TempArtifactRoot() as t:
        zero_results_body = b"<html><body>No results found for your search.</body></html>"
        result, _ = _run_pipeline(conn, t.path, _happy_path_responses(zero_results_body))
        assert isinstance(result, RecorderPipelineNotImported), result
        assert result.reason == "zero_results"
        _assert_zero_writes(conn, t.path)
    print("PASS: a zero-result response produces RecorderPipelineNotImported(reason='zero_results') and zero DB/artifact writes")


def test_multiple_results_produces_zero_writes():
    conn = _fresh_conn()
    _seed_source(conn)
    _seed_run(conn)
    with _TempArtifactRoot() as t:
        multi_body = _build_results_page_html([
            _build_row_html(document_number=TRANSFORMED, detail_href="/web/document/EXAMPLE_DOC000S000"),
            _build_row_html(document_number="TEST_ONLY_9999", detail_href="/web/document/EXAMPLE_DOC000S001"),
        ]).encode("utf-8")
        result, _ = _run_pipeline(conn, t.path, _happy_path_responses(multi_body))
        assert isinstance(result, RecorderPipelineNotImported), result
        assert result.reason == "multiple_results"
        _assert_zero_writes(conn, t.path)
    print("PASS: a multiple-result response produces RecorderPipelineNotImported(reason='multiple_results') and zero DB/artifact writes")


def test_document_number_mismatch_produces_zero_writes():
    conn = _fresh_conn()
    _seed_source(conn)
    _seed_run(conn)
    with _TempArtifactRoot() as t:
        mismatch_body = _build_results_page_html([_build_row_html(document_number="TEST_ONLY_DIFFERENT")]).encode("utf-8")
        result, _ = _run_pipeline(conn, t.path, _happy_path_responses(mismatch_body))
        assert isinstance(result, RecorderPipelineNotImported), result
        assert result.reason == "document_number_mismatch"
        _assert_zero_writes(conn, t.path)
    print("PASS: a returned document number that does not match the query produces RecorderPipelineNotImported(reason='document_number_mismatch') and zero DB/artifact writes")


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
