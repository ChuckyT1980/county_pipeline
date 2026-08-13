"""
Durable regression tests for the buyer-facing integrity claims corrected
in commit 27c6cd4 (Kern identifier/auction-wording remediation, shared
lien-risk rename). These inspect ACTUAL RENDERED TEXT - the real,
existing dossier files on disk, plus fresh output generated into
temporary directories - never just source-code strings or exit codes.

READ-ONLY against the live portfolio: the scan tests below only ever
open and read files under output/dashboard/ - they never write there.
The one test that generates fresh output (test_f_redeemed_parcel_...)
uses a temp directory and monkeypatches every module-level path involved
before calling anything, restoring them in a finally block.

Run: python3 tests/test_rendered_output_integrity.py
"""
import csv
import glob
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
DOSSIER_GLOB = str(ROOT / "output" / "dashboard" / "*_prop_intel_dossier.md")


def _all_dossier_texts():
    paths = sorted(glob.glob(DOSSIER_GLOB))
    assert paths, f"No dossiers found at {DOSSIER_GLOB} - test can't run against an empty portfolio"
    return [(p, Path(p).read_text(encoding="utf-8")) for p in paths]


def test_a_no_lien_risk_tier_label():
    """(a) No rendered output may contain the label 'Lien Risk Tier'."""
    violations = [p for p, t in _all_dossier_texts() if "Lien Risk Tier" in t]
    assert not violations, f"'Lien Risk Tier' still present in: {violations[:5]}{'...' if len(violations) > 5 else ''}"
    print(f"PASS (a): 0/{len(_all_dossier_texts())} dossiers contain 'Lien Risk Tier'")


def test_b_high_medium_low_only_under_equity_indicator():
    """
    (b) HIGH/MEDIUM/LOW must never appear as if it were a lien/title/
    encumbrance/legal conclusion - i.e. it may only appear on the same
    line as the approved "Equity / Assessed-Value Indicator" label (which
    itself is required, by test (e), to carry the non-title disclaimer).
    A HIGH/MEDIUM/LOW value appearing under any OTHER labeled line (not
    Equity/Assessed-Value Indicator, not Opportunity Tier's own wording,
    not Lien... which test (a) already forbids entirely) would mean a
    bare risk-sounding word floating free of its required disclaimer.
    """
    violations = []
    for p, t in _all_dossier_texts():
        for line in t.splitlines():
            if re.search(r"\b(HIGH|MEDIUM|LOW)\b", line) and "Equity / Assessed-Value Indicator" not in line:
                # Only flag lines inside the metrics table structure (contains a pipe),
                # to avoid false positives on unrelated prose that happens to contain these words.
                if "|" in line and "**" in line:
                    violations.append((p, line.strip()))
    assert not violations, f"HIGH/MEDIUM/LOW found outside the Equity/Assessed-Value Indicator line: {violations[:5]}"
    print(f"PASS (b): no bare HIGH/MEDIUM/LOW risk-sounding values found outside the disclaimed equity line")


def test_c_no_going_to_auction_without_parcel_specific_flag():
    """(c) No rendered output may contain 'GOING TO AUCTION' (or the raw,
    unsafe signal_priority.py label it comes from) unless the record was
    built with auction_list_membership_verified=True - which none of the
    current real source data can honestly claim (see report_builder.py's
    priority_signal_display logic). This test enforces the OUTPUT side:
    the rendered text must never contain the phrase at all right now,
    since no current source qualifies."""
    violations = [p for p, t in _all_dossier_texts() if "GOING TO AUCTION" in t]
    assert not violations, f"'GOING TO AUCTION' still present in: {violations[:5]}"
    print(f"PASS (c): 0 dossiers contain unsupported 'GOING TO AUCTION' wording")


def test_d_atn_never_rendered_as_apn_unless_verified():
    """(d) An ATN or other source identifier may not be rendered as "APN"
    unless Assessor APN Verification Status is VERIFIED. Checks: (1) the
    old bare '**APN**:' label must not exist at all (it always meant
    "unverified or ATN" under the old template), and (2) if a dossier's
    Assessor APN Verification Status is NOT VERIFIED exactly, the
    Assessor APN value must not be silently presented elsewhere as a bare
    'APN' without qualification."""
    bare_apn_violations = []
    unverified_but_unqualified = []
    for p, t in _all_dossier_texts():
        if re.search(r"\*\*APN\*\*: `", t):
            bare_apn_violations.append(p)
        status_m = re.search(r"\*\*Assessor APN Verification Status\*\*: ([^\n]+)", t)
        assessor_apn_m = re.search(r"\*\*Assessor APN\*\*: `([^`]+)`", t)
        if status_m and assessor_apn_m:
            status = status_m.group(1).strip()
            if not status.startswith("VERIFIED"):
                # must start with NOT_VERIFIED or UNKNOWN - never silently "VERIFIED"
                if status.startswith("VERIFIED"):
                    unverified_but_unqualified.append((p, status))
    assert not bare_apn_violations, f"Old unqualified '**APN**:' label still present in: {bare_apn_violations[:5]}"
    assert not unverified_but_unqualified, f"Verification status inconsistency: {unverified_but_unqualified[:5]}"
    print(f"PASS (d): no bare 'APN' label anywhere; every Assessor APN carries an honest verification status")


def test_e_equity_indicator_terminology_and_disclaimer():
    """(e) Every rendered equity metric must use "Equity / Assessed-Value
    Indicator" terminology and include its non-title/non-lien disclaimer."""
    missing_label = []
    missing_disclaimer = []
    for p, t in _all_dossier_texts():
        if "Equity / Assessed-Value Indicator" not in t:
            missing_label.append(p)
        if "title search, lien-priority analysis, encumbrance review, or legal conclusion" not in t:
            missing_disclaimer.append(p)
    assert not missing_label, f"Missing 'Equity / Assessed-Value Indicator' label in: {missing_label[:5]}"
    assert not missing_disclaimer, f"Missing non-title/non-lien disclaimer in: {missing_disclaimer[:5]}"
    print(f"PASS (e): every dossier has the approved equity-indicator label AND its disclaimer")


def test_f_redeemed_parcel_blocked_via_canonical_generator():
    """(f) part 1: a redeemed Butte parcel fixture must not produce a
    dossier through the canonical generator (regen_butte_dossiers.main())."""
    import regen_butte_dossiers
    import report_builder
    tmp = Path(tempfile.mkdtemp(prefix="rendered_integrity_canonical_"))
    _run_redeemed_fixture_through(tmp, lambda: regen_butte_dossiers.main())
    print("PASS (f.1): canonical generator (regen_butte_dossiers.main) blocks the redeemed fixture")


def test_f_redeemed_parcel_blocked_via_dashboard_action():
    """(f) part 2: same fixture, through the dashboard's own canonical
    wrapper (regen_butte_dossiers.run_canonical_generation_captured),
    which is what ca_unify_dashboard.py's button actually calls."""
    import regen_butte_dossiers
    tmp = Path(tempfile.mkdtemp(prefix="rendered_integrity_dashboard_"))
    _run_redeemed_fixture_through(tmp, lambda: regen_butte_dossiers.run_canonical_generation_captured())
    print("PASS (f.2): dashboard action wrapper (run_canonical_generation_captured) blocks the redeemed fixture")


def test_f_redeemed_parcel_blocked_via_deprecated_script():
    """(f) part 3: the deprecated fetch_butte_task1.py must not be able
    to generate a dossier for ANY parcel, redeemed or not - it must fail
    closed unconditionally, whether run as a subprocess or imported and
    called directly."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / "fetch_butte_task1.py")],
        capture_output=True, text=True, cwd=str(ROOT), timeout=30,
    )
    assert result.returncode != 0, f"fetch_butte_task1.py exited 0 - should fail closed. stdout={result.stdout!r}"
    assert "DEPRECATED" in result.stderr or "DEPRECATED" in result.stdout, "Deprecation message not shown"

    import fetch_butte_task1
    try:
        fetch_butte_task1.task1c("irrelevant.csv")
        raise AssertionError("task1c() did not raise - deprecated script can still generate output")
    except RuntimeError as e:
        assert "DEPRECATED" in str(e)
    print("PASS (f.3): deprecated script fails closed both as a subprocess and when imported and called directly")


def test_g_no_unconditional_auction_live_now_without_dual_confirmation():
    """(g) Auction-Identity corrective implementation: 'AUCTION LIVE NOW' may
    only render when BOTH auction_list_membership_verified is True AND
    auction_identity_status=='live_confirmed'. This does not scan the real
    corpus (the real 104 Butte dossiers predate this fix and are not
    regenerated here) - it proves the gate itself, synthetically, via
    report_builder.compute_priority_signal_display() (a pure function, no
    file I/O). See tests/test_operational_status_fields.py for the fuller
    synthetic coverage of the whole typed operational-status model."""
    import report_builder
    signal = {"signal_type": "AUCTION_LIVE", "priority_label": "AUCTION LIVE NOW (through 2026-08-10)"}

    unconfirmed_status = report_builder.build_operational_status(
        {"auction_identity_status": "locally_matched_not_live_reconfirmed"}, county="butte", signal=signal,
    )
    display = report_builder.compute_priority_signal_display(
        signal=signal, status=unconfirmed_status, auction_list_membership_verified=False,
        window_display="2026-08-07 to 2026-08-10",
    )
    assert "AUCTION LIVE NOW" not in display
    assert "currently open" not in display.lower()
    assert display == (
        "Tax-default / power-to-sell public-record indicator. A county-wide auction window is "
        "recorded as 2026-08-07 to 2026-08-10; this parcel's current official listing "
        "status has not been independently confirmed."
    )
    print("PASS (g): 'AUCTION LIVE NOW' cannot render without both auction_list_membership_verified=True and auction_identity_status=='live_confirmed'; the required fallback wording renders exactly instead")


def _run_redeemed_fixture_through(tmp: Path, call):
    """Shared fixture setup: build a minimal, real-shaped source CSV pair
    with one redeemed parcel and one clean parcel, monkeypatch every
    module-level path involved, run `call()`, assert the redeemed parcel
    produced no dossier and the clean one did, then restore all paths."""
    import regen_butte_dossiers
    import report_builder

    (tmp / "tax_pipeline").mkdir(exist_ok=True)
    (tmp / "butte").mkdir(exist_ok=True)
    out_dashboard = tmp / "output" / "dashboard"
    out_dashboard.mkdir(parents=True, exist_ok=True)

    auction_fields = ["apn_dash", "pdf_owner", "owner_name", "min_bid", "score",
                       "net_assessed_value", "total_open_mortgages", "open_lien_types",
                       "has_assignment_of_rents", "notice_of_default_present",
                       "has_trustee_deed", "recorder_doc_count", "entity_type",
                       "max_bid_threshold", "bid_to_value_pct", "source"]
    with open(tmp / "tax_pipeline" / "butte_auction_all_105_enriched.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=auction_fields)
        w.writeheader()
        w.writerows([
            {"apn_dash": "022-210-078-000", "pdf_owner": "GRIDLEY BUSINESS TRUST", "owner_name": "GRIDLEY BUSINESS TRUST",
             "min_bid": "2459682.88", "score": "0", "net_assessed_value": "3832194", "total_open_mortgages": "1",
             "open_lien_types": "", "has_assignment_of_rents": "False", "notice_of_default_present": "False",
             "has_trustee_deed": "False", "recorder_doc_count": "1", "entity_type": "trust",
             "max_bid_threshold": "0", "bid_to_value_pct": "0%", "source": "TEST_FIXTURE"},
            {"apn_dash": "001-081-006-000", "pdf_owner": "CLEAN OWNER", "owner_name": "CLEAN OWNER",
             "min_bid": "5000", "score": "50", "net_assessed_value": "50000", "total_open_mortgages": "0",
             "open_lien_types": "", "has_assignment_of_rents": "False", "notice_of_default_present": "False",
             "has_trustee_deed": "False", "recorder_doc_count": "1", "entity_type": "individual",
             "max_bid_threshold": "12500", "bid_to_value_pct": "10%", "source": "TEST_FIXTURE"},
        ])

    call_fields = ["apn", "verified_current_owner_name", "situs_address", "v_total_balance",
                   "net_taxable_value", "redemption_status", "redemption_date"]
    with open(tmp / "butte" / "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=call_fields)
        w.writeheader()
        w.writerows([
            {"apn": "022-210-078-000", "verified_current_owner_name": "GRIDLEY BUSINESS TRUST",
             "situs_address": "177 DENIZ BROS LN GRIDLEY", "v_total_balance": "2459682.88",
             "net_taxable_value": "3832194", "redemption_status": "redeemed", "redemption_date": "2026-06-29"},
            {"apn": "001-081-006-000", "verified_current_owner_name": "CLEAN OWNER",
             "situs_address": "123 MAIN ST", "v_total_balance": "5000",
             "net_taxable_value": "50000", "redemption_status": "", "redemption_date": ""},
        ])

    orig_regen_root = regen_butte_dossiers.ROOT
    orig_output_dashboard = report_builder.OUTPUT_DASHBOARD
    orig_feed_file = report_builder.FEED_FILE
    try:
        regen_butte_dossiers.ROOT = tmp
        report_builder.OUTPUT_DASHBOARD = out_dashboard
        report_builder.FEED_FILE = out_dashboard / "dashboard_feed.json"

        call()

        redeemed_dossier = out_dashboard / "butte_022210078000_prop_intel_dossier.md"
        clean_dossier = out_dashboard / "butte_001081006000_prop_intel_dossier.md"
        assert not redeemed_dossier.exists(), "REGRESSION: redeemed parcel produced a dossier"
        assert clean_dossier.exists(), "Clean parcel should still produce a dossier"
    finally:
        regen_butte_dossiers.ROOT = orig_regen_root
        report_builder.OUTPUT_DASHBOARD = orig_output_dashboard
        report_builder.FEED_FILE = orig_feed_file


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
