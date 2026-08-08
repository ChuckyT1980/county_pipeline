"""
Tests for lead_status.py's ACTIVE_CANDIDATE guarantee.

Run: python3 tests/test_lead_status.py
(No pytest dependency required - plain assertions, exits non-zero on failure.)
"""
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
