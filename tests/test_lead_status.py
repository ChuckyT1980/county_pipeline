"""
Tests for lead_status.py's ACTIVE_CANDIDATE guarantee.

Run: python3 tests/test_lead_status.py
(No pytest dependency required - plain assertions, exits non-zero on failure.)
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lead_status import LeadStatus, evaluate_lead

RUN_DATE = date(2026, 8, 8)


def test_past_deadline_is_always_expired_never_active():
    """The core regression test: an otherwise-valid record with a past
    deadline must be forced to EXPIRED, and must never reach ACTIVE_CANDIDATE
    - regardless of amount_disclosed or how confident the extraction was."""
    for amount_disclosed in (True, False):
        result = evaluate_lead(
            source_verified=True,
            deadline_raw="November 27, 2025",
            run_date=RUN_DATE,
            amount_disclosed=amount_disclosed,
        )
        assert result.status == LeadStatus.EXPIRED, f"Expected EXPIRED, got {result.status}"
        assert LeadStatus.ACTIVE_CANDIDATE not in result.history, "EXPIRED record must never touch ACTIVE_CANDIDATE"
    print("PASS: past deadline -> always EXPIRED, never ACTIVE_CANDIDATE")


def test_future_deadline_with_amount_reaches_active_via_possible():
    result = evaluate_lead(
        source_verified=True,
        deadline_raw="December 31, 2026",
        run_date=RUN_DATE,
        amount_disclosed=True,
    )
    assert result.status == LeadStatus.ACTIVE_CANDIDATE
    assert LeadStatus.CLAIMABILITY_POSSIBLE in result.history
    assert result.days_remaining is not None and result.days_remaining > 0
    print("PASS: future deadline + disclosed amount -> ACTIVE_CANDIDATE via CLAIMABILITY_POSSIBLE")


def test_future_deadline_without_amount_reaches_active_via_unconfirmed():
    result = evaluate_lead(
        source_verified=True,
        deadline_raw="December 31, 2026",
        run_date=RUN_DATE,
        amount_disclosed=False,
    )
    assert result.status == LeadStatus.ACTIVE_CANDIDATE
    assert LeadStatus.CLAIMABILITY_UNCONFIRMED in result.history
    print("PASS: future deadline + undisclosed amount -> ACTIVE_CANDIDATE via CLAIMABILITY_UNCONFIRMED")


def test_missing_deadline_never_reaches_active():
    result = evaluate_lead(source_verified=True, deadline_raw=None, run_date=RUN_DATE, amount_disclosed=True)
    assert result.status == LeadStatus.DEADLINE_UNVERIFIABLE
    assert LeadStatus.ACTIVE_CANDIDATE not in result.history
    print("PASS: missing deadline -> DEADLINE_UNVERIFIABLE, never ACTIVE_CANDIDATE")


def test_unparseable_deadline_never_reaches_active():
    result = evaluate_lead(source_verified=True, deadline_raw="sometime next year probably", run_date=RUN_DATE, amount_disclosed=True)
    assert result.status == LeadStatus.DEADLINE_UNVERIFIABLE
    assert LeadStatus.ACTIVE_CANDIDATE not in result.history
    print("PASS: unparseable deadline -> DEADLINE_UNVERIFIABLE, never ACTIVE_CANDIDATE")


def test_unsourced_record_never_reaches_active():
    result = evaluate_lead(source_verified=False, deadline_raw="December 31, 2026", run_date=RUN_DATE, amount_disclosed=True)
    assert result.status == LeadStatus.EXTRACTED
    assert result.history == [LeadStatus.EXTRACTED]
    print("PASS: unverified source -> stuck at EXTRACTED, never ACTIVE_CANDIDATE")


def test_nevada_regression_fixture():
    """
    The actual Nevada incident, replayed against the real fixture PDF.
    This is the regression test that must never silently start passing
    for the wrong reason - it pins the exact real-world case that
    motivated this whole module.
    """
    fixture = Path(__file__).parent / "fixtures" / "nevada_nov2024_excess_proceeds_EXPIRED.pdf"
    assert fixture.exists(), f"Regression fixture missing: {fixture}"

    from pypdf import PdfReader
    text = PdfReader(str(fixture)).pages[0].extract_text()

    # The real, stated deadline in the document (not the "Dec 19, 2026"
    # misread that caused the original incident).
    m = re.search(r"Claims must be filed by ([A-Za-z]+ \d{1,2}, \d{4})", text)
    assert m, "Fixture parsing broke - expected 'Claims must be filed by <date>' in the document text"
    deadline_raw = m.group(1)
    assert deadline_raw == "November 27, 2025", f"Fixture text changed unexpectedly: got '{deadline_raw}'"

    result = evaluate_lead(source_verified=True, deadline_raw=deadline_raw, run_date=RUN_DATE, amount_disclosed=False)
    assert result.status == LeadStatus.EXPIRED, (
        f"REGRESSION: the real Nevada fixture must evaluate to EXPIRED, got {result.status}. "
        f"This is the exact case that was originally misreported as active - if this test ever "
        f"passes with a non-EXPIRED status, the bug is back."
    )
    print("PASS: Nevada regression fixture correctly evaluates to EXPIRED")


def test_expired_sale_cycle_forces_expired_regardless_of_own_deadline():
    """
    Requirement #4: a county-level expired sale cycle must prevent EVERY
    linked dossier from becoming ACTIVE_CANDIDATE - even if that specific
    record's own printed deadline is (correctly or by error) future-dated.
    cycle_expired=True must win, unconditionally, checked first.
    """
    result = evaluate_lead(
        source_verified=True,
        deadline_raw="December 31, 2030",  # deliberately far-future, would normally be ACTIVE_CANDIDATE
        run_date=RUN_DATE,
        amount_disclosed=True,
        cycle_expired=True,
    )
    assert result.status == LeadStatus.EXPIRED, (
        f"A record whose sale cycle is expired must be EXPIRED even with a future-dated deadline, got {result.status}"
    )
    assert LeadStatus.ACTIVE_CANDIDATE not in result.history
    print("PASS: cycle_expired=True forces EXPIRED even when the record's own deadline is future-dated")


def test_no_status_can_be_set_outside_the_state_machine():
    """
    Requirement #5: report_builder.py must have NO independent path to
    set a dossier's lead status - it must be 100% derived from
    evaluate_lead(). Proven here by monkeypatching evaluate_lead to
    return a forced, distinctive value and confirming the actual
    generated dossier reflects EXACTLY that value, not something
    report_builder computed on its own.
    """
    import importlib
    import report_builder
    import lead_status as ls_module

    original = ls_module.evaluate_lead

    def fake_evaluate_lead(**kwargs):
        return ls_module.LeadEvaluation(
            status=ls_module.LeadStatus.EXPIRED,
            reason="FORCED_BY_TEST_SENTINEL_VALUE",
            history=[ls_module.LeadStatus.EXTRACTED, ls_module.LeadStatus.EXPIRED],
        )

    # report_builder imported evaluate_lead by name (`from lead_status import
    # evaluate_lead`), so the patch target is report_builder's own namespace,
    # not lead_status's - this is what actually proves report_builder calls
    # through the imported reference rather than having its own copy.
    report_builder.evaluate_lead = fake_evaluate_lead
    try:
        out_path = report_builder.build_excess_proceeds_report(
            {
                "apn_dash": "WIRING-TEST-000",
                "owner": "WIRING TEST",
                "excess_proceeds": 1000.0,
                "claim_deadline": "2099-01-01",  # would normally be far-future ACTIVE_CANDIDATE
                "source_file": "test",
                "verification": "test",
            },
            "test_county",
        )
        content = out_path.read_text(encoding="utf-8")
        assert "FORCED_BY_TEST_SENTINEL_VALUE" in content, (
            "report_builder did not use the patched evaluate_lead() - it may have an "
            "independent status-setting code path outside the state machine"
        )
        assert "**Status: EXPIRED**" in content, "report_builder's displayed status did not match the patched evaluate_lead() result"
    finally:
        report_builder.evaluate_lead = original
        out_path.unlink(missing_ok=True)
        # build_excess_proceeds_report() also appends an entry to
        # dashboard_feed.json - deleting the .md file alone leaves that
        # entry behind, polluting the live feed with test data.
        feed_file = report_builder.FEED_FILE
        if feed_file.exists():
            feed = json.loads(feed_file.read_text(encoding="utf-8"))
            feed = [e for e in feed if e.get("apn") != "WIRING-TEST-000"]
            feed_file.write_text(json.dumps(feed, indent=2), encoding="utf-8")
    print("PASS: report_builder has no status-setting path independent of evaluate_lead()")


def test_urgency_wording_never_implies_actionable_when_expired():
    """
    Regression for a second bug found while fixing the Nevada incident:
    predictive_scorer.score_excess_proceeds() used to render a past
    deadline as "RED EXTREME URGENCY (-255 days left)" - which reads as
    "act now, it's very time-sensitive," the opposite of the truth
    (it's over, not urgent). Must say EXPIRED, never "URGENCY".
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from predictive_scorer import score_excess_proceeds

    result = score_excess_proceeds({"excess_proceeds": 5000, "owner": "TEST", "claim_deadline": "2025-11-27"})
    urgency = result["urgency_status"]
    assert "EXPIRED" in urgency, f"Expected 'EXPIRED' in urgency_status, got: {urgency}"
    assert "URGENCY" not in urgency, f"Expired deadline must never say URGENCY (implies still actionable): {urgency}"
    print("PASS: expired deadline renders as EXPIRED, never as an urgency countdown")


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
