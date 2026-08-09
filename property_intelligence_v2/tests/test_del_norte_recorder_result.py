"""
Tests for property_intelligence_v2/extractors/del_norte_recorder_result.py.

All HTML fixtures in this file are inline and fully synthetic - no real
California document numbers, dates, names, result IDs, or raw HTML copied
from any live lookup. Values like "TEST_ONLY_0000", "EXAMPLE_GRANTOR_1", and
"01/01/1900" are placeholders. Structural markup (element/class names such
as "ss-search-row", "searchResultThreeColumn") reflects the vendor
platform's own generic UI structure, not identifying data, and is
reproduced because the parser matches against it exactly - the same
convention already used in test_del_norte_asrprint_extractor.py for that
module's field labels.

No database, no importer, no filesystem, no network - parse_recorder_results()
is a pure function and every test here calls it directly, with in-memory
values only. No temporary or scratch files are created by this file.

Run: python3 property_intelligence_v2/tests/test_del_norte_recorder_result.py
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "extractors"))

from del_norte_recorder_result import (  # noqa: E402
    RecorderResultsExtractionFailure,
    RecorderResultsExtractionInput,
    RecorderResultsExtractionSuccess,
    parse_recorder_results,
)
import del_norte_recorder_result as parser_module  # noqa: E402

PARSER_SOURCE = Path(parser_module.__file__).read_text(encoding="utf-8")

QUERY = "TEST_ONLY_0000"


def _build_row_html(
    *,
    document_number="TEST_ONLY_0000",
    instrument_type="EXAMPLE_TYPE",
    recording_date="01/01/1900",
    grantors=("EXAMPLE_GRANTOR_1",),
    grantees=("EXAMPLE_GRANTEE_1",),
    detail_href="/web/document/TEST_ONLY_DOC000S000",
    include_recording_date=True,
    include_grantor=True,
    include_grantee=True,
    include_instrument_type=True,
    extra_grantor_blocks=(),
    extra_grantee_blocks=(),
    book_page=None,  # None=absent column, ""=present but blank, "value"=populated
    apn=None,        # same tri-state convention
):
    header = document_number
    if include_instrument_type:
        header += f" • {instrument_type}"

    cols = []
    if include_recording_date:
        cols.append(f'<div class="searchResultThreeColumn"><li>Recording Date</li><li>{recording_date}</li></div>')
    if include_grantor:
        names_html = "".join(f"<li>{n}</li>" for n in grantors)
        cols.append(f'<div class="searchResultThreeColumn"><li>Grantor ({len(grantors)})</li>{names_html}</div>')
    for extra in extra_grantor_blocks:
        names_html = "".join(f"<li>{n}</li>" for n in extra)
        cols.append(f'<div class="searchResultThreeColumn"><li>Grantor ({len(extra)})</li>{names_html}</div>')
    if include_grantee:
        names_html = "".join(f"<li>{n}</li>" for n in grantees)
        cols.append(f'<div class="searchResultThreeColumn"><li>Grantee</li>{names_html}</div>')
    for extra in extra_grantee_blocks:
        names_html = "".join(f"<li>{n}</li>" for n in extra)
        cols.append(f'<div class="searchResultThreeColumn"><li>Grantee</li>{names_html}</div>')
    if book_page is not None:
        value_html = f"<li>{book_page}</li>" if book_page else ""
        cols.append(f'<div class="searchResultThreeColumn"><li>Book/Page</li>{value_html}</div>')
    if apn is not None:
        value_html = f"<li>{apn}</li>" if apn else ""
        cols.append(f'<div class="searchResultThreeColumn"><li>APN</li>{value_html}</div>')

    detail_link = f'<a href="{detail_href}">View</a>' if detail_href else ""

    return f"""
<li class="ss-search-row">
  <h1>{header}</h1>
  {"".join(cols)}
  {detail_link}
</li>
"""


def _build_page_html(rows_html):
    return f"""
<html><body>
<ul id="searchResultsList">
{"".join(rows_html)}
</ul>
</body></html>
"""


def _parse(html, query=QUERY, search_id="TEST_ONLY_SEARCH_ID"):
    return parse_recorder_results(RecorderResultsExtractionInput(
        queried_document_number_transformed=query,
        raw_html=html,
        search_id=search_id,
    ))


def test_one_clean_matching_result():
    html = _build_page_html([_build_row_html(document_number=QUERY)])
    result = _parse(html)
    assert isinstance(result, RecorderResultsExtractionSuccess), result
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.document_number == QUERY
    assert row.document_number_matches_query is True
    assert row.recording_date_raw == "01/01/1900"
    assert row.instrument_type_raw == "EXAMPLE_TYPE"
    assert row.grantors == ("EXAMPLE_GRANTOR_1",)
    assert row.grantees == ("EXAMPLE_GRANTEE_1",)
    assert row.detail_link_path == "/web/document/TEST_ONLY_DOC000S000"
    assert row.book_page_present is False
    assert row.book_page_raw_or_none is None
    assert row.apn_present is False
    assert row.apn_raw_or_none is None
    assert row.warnings == ()
    assert result.warnings == ()
    print("PASS: one clean matching result extracts every field with zero warnings")


def test_zero_results():
    html = "<html><body><p>No results found for your search.</p></body></html>"
    result = _parse(html)
    assert isinstance(result, RecorderResultsExtractionSuccess), result
    assert result.rows == ()
    codes = [w.code for w in result.warnings]
    assert codes == ["ZERO_RESULTS"], codes
    print("PASS: a zero-results page is Success with rows=() and ZERO_RESULTS warning, not a failure")


def test_multiple_results():
    html = _build_page_html([
        _build_row_html(document_number=QUERY, detail_href="/web/document/TEST_ONLY_DOC000S000"),
        _build_row_html(document_number="TEST_ONLY_9999", detail_href="/web/document/TEST_ONLY_DOC000S001"),
    ])
    result = _parse(html)
    assert isinstance(result, RecorderResultsExtractionSuccess), result
    assert len(result.rows) == 2
    codes = [w.code for w in result.warnings]
    assert codes == ["MULTIPLE_RESULTS_RETURNED"], codes
    print("PASS: a multiple-results page is Success with both rows preserved and MULTIPLE_RESULTS_RETURNED warning")


def test_document_number_mismatch():
    html = _build_page_html([_build_row_html(document_number="TEST_ONLY_DIFFERENT")])
    result = _parse(html, query=QUERY)
    assert isinstance(result, RecorderResultsExtractionSuccess), result
    row = result.rows[0]
    assert row.document_number_matches_query is False
    mismatch = [w for w in row.warnings if w.code == "DOCUMENT_NUMBER_MISMATCH"]
    assert len(mismatch) == 1
    print("PASS: a mismatched document number is Success with a row-level DOCUMENT_NUMBER_MISMATCH warning")


def test_missing_recording_date():
    html = _build_page_html([_build_row_html(document_number=QUERY, include_recording_date=False)])
    result = _parse(html)
    row = result.rows[0]
    assert row.recording_date_raw is None
    codes = [w.code for w in row.warnings]
    assert "MISSING_RECORDING_DATE" in codes
    print("PASS: a missing Recording Date column produces MISSING_RECORDING_DATE, not a failure")


def test_missing_instrument_type():
    html = _build_page_html([_build_row_html(document_number=QUERY, include_instrument_type=False)])
    result = _parse(html)
    row = result.rows[0]
    assert row.instrument_type_raw is None
    codes = [w.code for w in row.warnings]
    assert "MISSING_INSTRUMENT_TYPE" in codes
    print("PASS: a missing instrument-type header segment produces MISSING_INSTRUMENT_TYPE, not a failure")


def test_missing_grantor_section():
    html = _build_page_html([_build_row_html(document_number=QUERY, include_grantor=False)])
    result = _parse(html)
    row = result.rows[0]
    assert row.grantors == ()
    codes = [w.code for w in row.warnings]
    assert "MISSING_GRANTOR_SECTION" in codes
    print("PASS: a missing Grantor column produces MISSING_GRANTOR_SECTION and an empty grantors tuple")


def test_missing_grantee_section():
    html = _build_page_html([_build_row_html(document_number=QUERY, include_grantee=False)])
    result = _parse(html)
    row = result.rows[0]
    assert row.grantees == ()
    codes = [w.code for w in row.warnings]
    assert "MISSING_GRANTEE_SECTION" in codes
    print("PASS: a missing Grantee column produces MISSING_GRANTEE_SECTION and an empty grantees tuple")


def test_duplicate_grantor_blocks_preserve_all_entries_in_order():
    html = _build_page_html([_build_row_html(
        document_number=QUERY,
        grantors=("EXAMPLE_GRANTOR_1", "EXAMPLE_GRANTOR_1"),
        extra_grantor_blocks=[("EXAMPLE_GRANTOR_2",)],
    )])
    result = _parse(html)
    row = result.rows[0]
    assert row.grantors == ("EXAMPLE_GRANTOR_1", "EXAMPLE_GRANTOR_1", "EXAMPLE_GRANTOR_2"), row.grantors
    dup = [w for w in row.warnings if w.code == "DUPLICATE_PARTY_SECTION" and w.field_name_or_none == "grantors"]
    assert len(dup) == 1
    print("PASS: duplicate Grantor blocks preserve every entry, including repeats, in exact source order, plus one DUPLICATE_PARTY_SECTION warning")


def test_duplicate_grantee_blocks_preserve_all_entries_in_order():
    html = _build_page_html([_build_row_html(
        document_number=QUERY,
        grantees=("EXAMPLE_GRANTEE_1",),
        extra_grantee_blocks=[("EXAMPLE_GRANTEE_2",), ("EXAMPLE_GRANTEE_1",)],
    )])
    result = _parse(html)
    row = result.rows[0]
    assert row.grantees == ("EXAMPLE_GRANTEE_1", "EXAMPLE_GRANTEE_2", "EXAMPLE_GRANTEE_1"), row.grantees
    dup = [w for w in row.warnings if w.code == "DUPLICATE_PARTY_SECTION" and w.field_name_or_none == "grantees"]
    assert len(dup) == 1
    print("PASS: duplicate Grantee blocks preserve every entry, including repeats, in exact source order, plus one DUPLICATE_PARTY_SECTION warning")


def test_book_page_absent_blank_and_populated():
    absent = _parse(_build_page_html([_build_row_html(document_number=QUERY, book_page=None)])).rows[0]
    assert absent.book_page_present is False
    assert absent.book_page_raw_or_none is None

    blank = _parse(_build_page_html([_build_row_html(document_number=QUERY, book_page="")])).rows[0]
    assert blank.book_page_present is True
    assert blank.book_page_raw_or_none is None

    populated = _parse(_build_page_html([_build_row_html(document_number=QUERY, book_page="EXAMPLE_000/000")])).rows[0]
    assert populated.book_page_present is True
    assert populated.book_page_raw_or_none == "EXAMPLE_000/000"
    print("PASS: book/page correctly distinguishes absent, present-but-blank, and populated states")


def test_apn_absent_blank_and_populated():
    absent = _parse(_build_page_html([_build_row_html(document_number=QUERY, apn=None)])).rows[0]
    assert absent.apn_present is False
    assert absent.apn_raw_or_none is None

    blank = _parse(_build_page_html([_build_row_html(document_number=QUERY, apn="")])).rows[0]
    assert blank.apn_present is True
    assert blank.apn_raw_or_none is None

    populated = _parse(_build_page_html([_build_row_html(document_number=QUERY, apn="000-000-000-000")])).rows[0]
    assert populated.apn_present is True
    assert populated.apn_raw_or_none == "000-000-000-000"
    print("PASS: APN correctly distinguishes absent, present-but-blank, and populated states")


def test_expected_relative_detail_link_no_warning():
    html = _build_page_html([_build_row_html(document_number=QUERY, detail_href="/web/document/TEST_ONLY_DOC000S000")])
    row = _parse(html).rows[0]
    assert row.detail_link_path == "/web/document/TEST_ONLY_DOC000S000"
    assert not any(w.code == "UNEXPECTED_DETAIL_LINK_FORM" for w in row.warnings)
    print("PASS: an expected relative /web/document/... detail link is stored with no warning")


def test_unexpected_detail_link_retained_with_warning():
    html = _build_page_html([_build_row_html(document_number=QUERY, detail_href="https://example.invalid/some/other/path")])
    row = _parse(html).rows[0]
    assert row.detail_link_path == "https://example.invalid/some/other/path", "unexpected link text must still be retained verbatim"
    assert any(w.code == "UNEXPECTED_DETAIL_LINK_FORM" for w in row.warnings)
    print("PASS: an absolute/unexpected detail link is retained verbatim plus UNEXPECTED_DETAIL_LINK_FORM, never followed")


def test_unrecognized_page_structure_is_typed_failure():
    html = "<html><body><p>TEST_ONLY_ some unrelated page content, e.g. a disclaimer page</p></body></html>"
    result = _parse(html)
    assert isinstance(result, RecorderResultsExtractionFailure), result
    assert result.classification == "schema_mismatch"
    assert result.next_action == "human_review"
    print("PASS: an unrecognized page shape (no result rows, no zero-results pattern) is a typed failure, never raises")


def test_malformed_input_is_typed_failure():
    for bad_html in ("", "not even html", "<<<>>>garbage&&&"):
        result = _parse(bad_html)
        assert isinstance(result, RecorderResultsExtractionFailure), (bad_html, result)
        assert result.classification == "schema_mismatch"
    print("PASS: malformed/empty input never raises and always returns a typed failure")


def test_parser_source_is_pure_no_db_network_file_or_importer_access():
    # AST-based, not substring matching: this file's own docstring
    # legitimately mentions "legacy_evidence_importer" and "sqlite3" in
    # prose - a substring scan would false-positive on the sentence
    # explaining the rule, exactly as already documented as having
    # happened (and been fixed) in test_del_norte_asrprint_extractor.py.
    tree = ast.parse(PARSER_SOURCE, filename=parser_module.__file__)
    imported_modules = set()
    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    forbidden_modules = {
        "sqlite3", "socket", "urllib", "urllib.request", "http", "http.client",
        "requests", "httpx", "legacy_evidence_importer", "del_norte_asrprint_pipeline",
        "del_norte_recorder_tyler",
    }
    hit_modules = imported_modules & forbidden_modules
    assert not hit_modules, hit_modules

    forbidden_calls = {"open", "connect", "urlopen"}
    hit_calls = called_names & forbidden_calls
    assert not hit_calls, hit_calls
    print("PASS: del_norte_recorder_result.py never imports sqlite3/network/importer modules and never calls open()/connect()/urlopen() (checked via AST)")


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
