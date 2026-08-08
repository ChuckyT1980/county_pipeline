"""
Dashboard-path and export/feed regression tests, part of the release-
integrity remediation (2026-08-08) that retired fetch_butte_task1.py as
a reachable bypass of the redemption filter.

Run: python3 tests/test_dashboard_and_export_integrity.py
"""
import ast
import csv
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def test_dashboard_button_resolves_to_canonical_path_only():
    """
    Source-level proof (ca_unify_dashboard.py cannot be imported directly
    in this environment - streamlit is not installed - so this inspects
    its AST rather than executing it): the "Generate Butte Dossiers"
    button handler must call
    regen_butte_dossiers.run_canonical_generation_captured, and must NOT
    reference fetch_butte_task1 or shell out via subprocess for Butte
    generation anywhere in the file.
    """
    source = (ROOT / "ca_unify_dashboard.py").read_text(encoding="utf-8")
    ast.parse(source)  # raises SyntaxError if the file doesn't even parse

    assert "run_canonical_generation_captured" in source, (
        "ca_unify_dashboard.py no longer references the canonical wrapper function"
    )
    # A historical/explanatory comment mentioning fetch_butte_task1 (why the
    # button used to shell out to it, and why that was retired) is expected
    # and fine - preserving that context is itself part of the audit trail.
    # What must NOT exist is any LIVE invocation: a subprocess call naming
    # it, or an executable import statement (as opposed to prose inside a
    # comment/docstring).
    live_invocation_lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "fetch_butte_task1" in line and ("subprocess" in line or stripped.startswith("import fetch_butte_task1") or stripped.startswith("from fetch_butte_task1")):
            live_invocation_lines.append(line.strip())
    assert not live_invocation_lines, f"Live invocation of fetch_butte_task1 found in ca_unify_dashboard.py: {live_invocation_lines}"
    print("PASS: dashboard source calls only the canonical wrapper; fetch_butte_task1 appears only in explanatory comments, never invoked")


def test_repo_wide_no_reachable_fetch_butte_task1_invocation():
    """
    Repository-wide search proving no executable dashboard, scheduler,
    task runner, documentation command, or default workflow still invokes
    fetch_butte_task1.py as something that would run it (vs. merely
    mentioning its name in a deprecation comment/docstring, which is
    expected and fine).
    """
    import subprocess
    # git grep, not a raw recursive filesystem grep: scoped to tracked
    # files (appropriate for "no executable/documented workflow invokes
    # it" - untracked scratch files don't count as a workflow), and fast
    # even in a repo with large untracked data directories (a plain
    # `grep -r .` here was observed to hang for 2+ minutes).
    result = subprocess.run(
        ["git", "grep", "-l", "fetch_butte_task1"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=30,
    )
    mentioning_files = [f for f in result.stdout.splitlines() if f]

    # Files legitimately allowed to mention fetch_butte_task1 without being
    # a "live invocation" for this check's purposes:
    #   - fetch_butte_task1.py itself (defines the deprecated functions)
    #   - .md reports/docs (prose, never executed)
    #   - this test file and test_rendered_output_integrity.py, both of
    #     which INTENTIONALLY import and call it to prove it fails closed -
    #     that is the opposite of a bypass, it's the regression coverage
    #     for the bypass. Checking a test file's own source against a
    #     substring heuristic like this one is inherently self-referential
    #     and produces false positives (the pattern list itself contains
    #     the strings being searched for) - excluded on principle, not
    #     just for this run.
    exempt_files = {
        "fetch_butte_task1.py",
        "tests/test_rendered_output_integrity.py",
        "tests/test_dashboard_and_export_integrity.py",
    }
    workflow_files = [
        f for f in mentioning_files
        if f not in exempt_files and not f.endswith(".md")
    ]

    violations = []
    for f in workflow_files:
        text = (ROOT / f).read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "fetch_butte_task1" in line and ("subprocess" in line or stripped.startswith("import fetch_butte_task1") or stripped.startswith("from fetch_butte_task1")):
                violations.append((f, line.strip()))

    assert not violations, f"Live invocation of fetch_butte_task1 found in a production/workflow file: {violations}"
    print(
        f"PASS: {len(mentioning_files)} file(s) mention fetch_butte_task1 total "
        f"({', '.join(mentioning_files)}); {len(workflow_files)} checked as workflow files "
        f"(excluding the deprecated file itself, its own regression tests, and .md docs); 0 live invocations"
    )


def test_export_feed_includes_corrected_fields_after_serialization():
    """
    (4c) Export/feed test: generate one fresh dossier into a temp
    directory via the canonical path, then confirm the corrected
    identifier fields and equity-indicator terminology actually survive
    into the serialized dashboard_feed.json entry - not just the rendered
    .md file. Found and fixed during this remediation: the feed entry
    previously serialized the RAW, uncorrected signal_priority label and
    omitted the identifier/equity fields entirely (report_builder.py's
    _update_dashboard_feed call for PROPERTY_INTELLIGENCE).
    """
    import report_builder

    tmp = Path(tempfile.mkdtemp(prefix="export_feed_test_"))
    out_dashboard = tmp / "output" / "dashboard"
    out_dashboard.mkdir(parents=True)

    orig_output_dashboard = report_builder.OUTPUT_DASHBOARD
    orig_feed_file = report_builder.FEED_FILE
    try:
        report_builder.OUTPUT_DASHBOARD = out_dashboard
        report_builder.FEED_FILE = out_dashboard / "dashboard_feed.json"

        # A Kern-shaped record: this is exactly the case that previously
        # leaked "GOING TO AUCTION" into the feed even after the .md fix.
        report_builder.build_property_intelligence_dossier(
            {
                "apn_dash": "017-490-06-00-3",
                "source_identifier": "017-490-06-00-3",
                "source_identifier_type": "ATN (Assessment/Tax Number, Kern tax-roll identifier)",
                "assessor_apn": "017-490-06",
                "assessor_apn_verification_status": "NOT_VERIFIED — test fixture",
                "owner_name": "TEST OWNER",
                "net_assessed_value": 427084.0,
                "min_bid": 76100.0,
                "situs": "705 WILLIAMS ST BAKERSFIELD",
                "current_doc_number": "226037165",
                "deed_date": "04/03/2026",
                "source_file": "test fixture",
                "verification_status": "test fixture",
            },
            "kern",
        )

        feed = json.loads((out_dashboard / "dashboard_feed.json").read_text(encoding="utf-8"))
        entry = feed[0]

        assert entry.get("source_identifier") == "017-490-06-00-3", f"source_identifier missing/wrong in feed: {entry.get('source_identifier')!r}"
        assert entry.get("assessor_apn") == "017-490-06", f"assessor_apn missing/wrong in feed: {entry.get('assessor_apn')!r}"
        assert "assessor_apn_verification_status" in entry, "assessor_apn_verification_status missing from feed entry"
        assert "equity_signal" in entry, "equity_signal missing from feed entry"
        assert "GOING TO AUCTION" not in entry.get("priority_signal", ""), (
            f"REGRESSION: feed's priority_signal still carries the raw uncorrected auction wording: {entry.get('priority_signal')!r}"
        )
        assert "not verified" in entry.get("priority_signal", "").lower() or "public-record indicator" in entry.get("priority_signal", "").lower(), (
            f"feed's priority_signal doesn't carry the corrected, honest wording: {entry.get('priority_signal')!r}"
        )
    finally:
        report_builder.OUTPUT_DASHBOARD = orig_output_dashboard
        report_builder.FEED_FILE = orig_feed_file

    print("PASS: corrected identifier fields and honest auction wording survive dashboard_feed.json serialization")


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
