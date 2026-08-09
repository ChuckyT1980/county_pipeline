"""
Tests for property_intelligence_v2/extractors/del_norte_asrprint.py.

All HTML fixtures in this file are inline and fully synthetic - no real
California names, APNs, addresses, dollar amounts, HTML, or copied page
fragments. Values like "000-000-000-000", "$1,000", and
"1 TEST_ONLY EXAMPLE ST" are placeholders; the field LABEL text (e.g.
"Assessor Parcel Number(APN)") is the vendor platform's own generic UI
copy, not identifying data, and is reproduced because the parser matches
against it exactly.

No database, no importer, no filesystem, no network - parse_asrprint() is
a pure function and every test here calls it directly.

Run: python3 property_intelligence_v2/tests/test_del_norte_asrprint_extractor.py
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "extractors"))

from del_norte_asrprint import (  # noqa: E402
    CONFIDENCE_VALUE,
    KNOWN_LABEL_TO_FIELD_NAME,
    REQUIRED_LABEL,
    RELATED_LINK_FIELD_NAME,
    AsrPrintExtractionFailure,
    AsrPrintExtractionInput,
    AsrPrintExtractionSuccess,
    parse_asrprint,
)
import del_norte_asrprint as extractor_module  # noqa: E402

EXTRACTOR_SOURCE = Path(extractor_module.__file__).read_text(encoding="utf-8")

# All 22 known labels with fully synthetic values - none plausible as real
# county data. Order matches KNOWN_LABEL_TO_FIELD_NAME for readability only;
# the parser does not care about row order.
ALL_22_ROWS = [
    ("Assessor Parcel Number(APN)", "000-000-000-000"),
    ("Assessment Number", "000-000-000-000"),
    ("Tax Rate Area(TRA)", "000000"),
    ("Current Document Number", "2000T0000"),
    ("Current Document  Date", "1/1/2000"),  # double space, matches real source quirk
    ("SitusAddr", "1 TEST_ONLY EXAMPLE ST TEST_ONLY CITY 00000"),
    ("Property Type", "TEST_ONLY VACANT LAND"),
    ("Lot Size(Acres)", "1.00"),
    ("Lot Size(SqFt)", "0.00"),
    ("Asmt Description", "TEST_ONLY LOT 1, EXAMPLE TRACT"),
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
assert len(ALL_22_ROWS) == 22


def _build_html(rows, *, back_href="/mbap/delnorte/asr/AsrMain/000000000000", include_back_link=True):
    row_html = "\n".join(
        f'<tr><td class="font-weight-bolder">{label}</td><td>{value}</td></tr>'
        for label, value in rows
    )
    back_html = f'<a id="Back" href="{back_href}">BACK</a>' if include_back_link else ""
    return f"""
<html lang="en-us">
<head><title>Print | Delnorte  County </title></head>
<body>
{back_html}
<section>
<table class="table table-active">
<caption>Property Information</caption>
{row_html}
<table class="table table-active">
<caption>Roll Values</caption>
</table>
</table>
</section>
</body>
</html>
"""


def _parse(html: str):
    return parse_asrprint(AsrPrintExtractionInput(
        legacy_path=Path("del_norte/raw_evidence/TEST_ONLY_fixture.html"),
        raw_html=html,
        filename="TEST_ONLY_fixture.html",
    ))


def test_full_22_field_success():
    result = _parse(_build_html(ALL_22_ROWS))
    assert isinstance(result, AsrPrintExtractionSuccess), result
    field_names = {f.field_name for f in result.observation_fields}
    expected_field_names = set(KNOWN_LABEL_TO_FIELD_NAME.values()) | {RELATED_LINK_FIELD_NAME}
    assert field_names == expected_field_names, field_names ^ expected_field_names
    assert all(f.confidence == "carried_forward" for f in result.observation_fields)
    assert not any(f.confidence == "confirmed" for f in result.observation_fields), \
        "archived local HTML is never confidence='confirmed' - see the module's Confidence value section"
    assert result.warnings == (), result.warnings
    assert len(result.identifier_candidates) == 3
    print("PASS: all 22 known fields plus the related link are extracted, all confidence='carried_forward', zero warnings")


def test_optional_field_omitted_produces_warning_not_failure():
    rows = [r for r in ALL_22_ROWS if r[0] != "Structural Imprv"]
    result = _parse(_build_html(rows))
    assert isinstance(result, AsrPrintExtractionSuccess), result
    assert "roll_value_structural_improvements" not in {f.field_name for f in result.observation_fields}
    missing_warnings = [w for w in result.warnings if w.code == "OPTIONAL_FIELD_MISSING"]
    assert len(missing_warnings) == 1
    assert missing_warnings[0].field_name_or_none == "roll_value_structural_improvements"
    print("PASS: a missing optional field produces OPTIONAL_FIELD_MISSING, not a failure")


def test_missing_required_apn_produces_failure():
    rows = [r for r in ALL_22_ROWS if r[0] != REQUIRED_LABEL]
    result = _parse(_build_html(rows))
    assert isinstance(result, AsrPrintExtractionFailure), result
    assert result.classification == "schema_mismatch"
    assert result.next_action == "human_review"
    assert "Assessor Parcel Number" in result.message
    print("PASS: a missing required APN produces AsrPrintExtractionFailure(schema_mismatch, human_review)")


def test_unknown_label_produces_warning_and_is_skipped():
    rows = ALL_22_ROWS + [("Mystery Field Not In Contract", "some value")]
    result = _parse(_build_html(rows))
    assert isinstance(result, AsrPrintExtractionSuccess), result
    unknown_warnings = [w for w in result.warnings if w.code == "UNRECOGNIZED_LABEL"]
    assert len(unknown_warnings) == 1
    assert unknown_warnings[0].raw_label_or_none == "Mystery Field Not In Contract"
    field_names = {f.field_name for f in result.observation_fields}
    assert not any("mystery" in fn.lower() for fn in field_names)
    print("PASS: an unrecognized label produces UNRECOGNIZED_LABEL and is never mapped to any field_name")


def test_duplicate_conflicting_label_produces_warning_and_keeps_first_value():
    rows = ALL_22_ROWS + [("Land", "$9,999")]  # conflicts with the real "Land" row's $1,000
    result = _parse(_build_html(rows))
    assert isinstance(result, AsrPrintExtractionSuccess), result
    dup_warnings = [w for w in result.warnings if w.code == "DUPLICATE_LABEL_OBSERVED"]
    assert len(dup_warnings) == 1
    assert dup_warnings[0].raw_label_or_none == "Land"
    land_fields = [f for f in result.observation_fields if f.field_name == "roll_value_land"]
    assert len(land_fields) == 1, "must not produce two observation fields for the same field_name"
    assert land_fields[0].field_value == "$1,000", "the FIRST observed value must be kept"
    print("PASS: a duplicate label with a conflicting value produces DUPLICATE_LABEL_OBSERVED and keeps only the first value")


def test_duplicate_consistent_label_produces_no_warning():
    rows = ALL_22_ROWS + [("Land", "$1,000")]  # same label, SAME value - not a conflict
    result = _parse(_build_html(rows))
    assert isinstance(result, AsrPrintExtractionSuccess), result
    dup_warnings = [w for w in result.warnings if w.code == "DUPLICATE_LABEL_OBSERVED"]
    assert dup_warnings == [], "a repeated label with an identical value is not a conflict"
    print("PASS: a duplicate label with the identical value produces no warning")


def test_malformed_page_produces_failure():
    for bad_html in ("<html><body>Not an AsrPrint page at all</body></html>", "", "not even html"):
        result = _parse(bad_html)
        assert isinstance(result, AsrPrintExtractionFailure), (bad_html, result)
        assert result.classification == "schema_mismatch"
    print("PASS: pages with no recognizable AsrPrint structure produce AsrPrintExtractionFailure, never raise")


def test_related_link_extracted_when_present_and_absent_when_missing():
    with_link = _parse(_build_html(ALL_22_ROWS, back_href="/mbap/delnorte/asr/AsrMain/000000000000", include_back_link=True))
    assert isinstance(with_link, AsrPrintExtractionSuccess)
    link_fields = [f for f in with_link.observation_fields if f.field_name == RELATED_LINK_FIELD_NAME]
    assert len(link_fields) == 1
    assert link_fields[0].field_value == "/mbap/delnorte/asr/AsrMain/000000000000"
    assert link_fields[0].confidence == "carried_forward"

    without_link = _parse(_build_html(ALL_22_ROWS, include_back_link=False))
    assert isinstance(without_link, AsrPrintExtractionSuccess)
    assert not any(f.field_name == RELATED_LINK_FIELD_NAME for f in without_link.observation_fields)
    assert not any(w.field_name_or_none == RELATED_LINK_FIELD_NAME for w in without_link.warnings), \
        "a missing related link is not one of the 22 known table labels and must not produce OPTIONAL_FIELD_MISSING"
    print("PASS: assessor_portal_related_link is extracted separately from the 22 table labels when present, and silently absent (no warning) when not")


def test_every_emitted_field_is_carried_forward_never_confirmed():
    """Dedicated proof, independent of test_full_22_field_success above:
    archived local HTML is never confidence='confirmed', with and without
    the related link present. See del_norte_asrprint.py's and
    extractors/README.md's "Confidence value" sections for why."""
    assert CONFIDENCE_VALUE == "carried_forward"

    with_link = _parse(_build_html(ALL_22_ROWS, include_back_link=True))
    assert isinstance(with_link, AsrPrintExtractionSuccess)
    assert len(with_link.observation_fields) > 0
    for f in with_link.observation_fields:
        assert f.confidence == "carried_forward", f
        assert f.confidence != "confirmed", f

    without_link = _parse(_build_html(ALL_22_ROWS, include_back_link=False))
    assert isinstance(without_link, AsrPrintExtractionSuccess)
    assert len(without_link.observation_fields) > 0
    for f in without_link.observation_fields:
        assert f.confidence == "carried_forward", f
        assert f.confidence != "confirmed", f
    print("PASS: every emitted ObservationFieldInput uses confidence='carried_forward', never 'confirmed', with and without the related link")


def test_identifier_candidates_are_in_memory_only_and_correctly_typed():
    result = _parse(_build_html(ALL_22_ROWS))
    assert isinstance(result, AsrPrintExtractionSuccess)
    by_type = {c.identifier_type: c for c in result.identifier_candidates}
    assert set(by_type.keys()) == {"ASSESSOR_APN", "OTHER_SOURCE_IDENTIFIER", "RECORDER_DOCUMENT_NUMBER"}

    apn = by_type["ASSESSOR_APN"]
    assert apn.value_raw == "000-000-000-000"
    assert apn.value_normalized_or_none == "000000000000"
    assert apn.verification_status == "SOURCE_ASSERTED"

    doc_number = by_type["RECORDER_DOCUMENT_NUMBER"]
    assert doc_number.value_raw == "2000T0000"
    assert doc_number.value_normalized_or_none is None, "no normalized form is proposed for recorder document numbers yet"

    # In-memory only: identifier candidates must never leak into observation_fields
    # under any field_name - the two are entirely separate return values.
    observation_field_names = {f.field_name for f in result.observation_fields}
    assert "ASSESSOR_APN" not in observation_field_names
    assert not any("identifier" in fn.lower() for fn in observation_field_names)
    print("PASS: identifier candidates are correctly typed and exist only on AsrPrintExtractionSuccess.identifier_candidates, never inside observation_fields")


def test_no_raw_normalized_duplicate_observation_fields():
    result = _parse(_build_html(ALL_22_ROWS))
    assert isinstance(result, AsrPrintExtractionSuccess)
    field_names = [f.field_name for f in result.observation_fields]
    assert len(field_names) == len(set(field_names)), "no field_name may repeat"
    assert not any(fn.endswith("_raw") or fn.endswith("_normalized") for fn in field_names), \
        "no observation field may be a raw/normalized duplicate pair"
    print("PASS: no observation field is a raw/normalized duplicate of another")


def test_extractor_source_never_imports_the_importer_or_a_database():
    # AST-based, not substring matching: this file's own docstrings AND
    # inline comments legitimately mention "legacy_evidence_importer" in
    # prose (e.g. "no call into legacy_evidence_importer anywhere in this
    # file") - a substring scan would false-positive on the very sentence
    # explaining the rule (confirmed: it did, twice, before this rewrite).
    # Parsing the actual import statements is precise and immune to that.
    tree = ast.parse(EXTRACTOR_SOURCE, filename=extractor_module.__file__)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert "sqlite3" not in imported_modules, imported_modules
    assert "legacy_evidence_importer" not in imported_modules, imported_modules
    print("PASS: del_norte_asrprint.py never imports sqlite3 or legacy_evidence_importer (checked via AST, immune to docstring/comment false positives)")


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
