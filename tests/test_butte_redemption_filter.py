"""
Regression test for the Butte redemption-filter bug (found and fixed
2026-08-08): regen_butte_dossiers.py never checked the call sheet's own
redemption_status field, so a redeemed parcel (real case: Gridley,
022-210-078-000) could be silently regenerated as a live opportunity on
any future run. This test proves the fix with a redeemed-parcel fixture
that WOULD have been regenerated before the fix - not just a unit check
of is_redeemed() in isolation, but a real end-to-end run through
regen_butte_dossiers.main() and report_builder.build_property_intelligence_dossier(),
using a temp directory so it never touches the real output/dashboard/.

Run: python3 tests/test_butte_redemption_filter.py
(No pytest dependency required - plain assertions, matching
tests/test_lead_status.py's convention.)
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import regen_butte_dossiers
import report_builder


def test_is_redeemed_unit():
    assert regen_butte_dossiers.is_redeemed({"redemption_status": "redeemed"}) is True
    assert regen_butte_dossiers.is_redeemed({"redemption_status": "Redeemed"}) is True  # case-insensitive
    assert regen_butte_dossiers.is_redeemed({"redemption_status": "  redeemed  "}) is True  # whitespace
    assert regen_butte_dossiers.is_redeemed({"redemption_status": ""}) is False
    assert regen_butte_dossiers.is_redeemed({}) is False
    print("PASS: is_redeemed() unit checks")


def test_redeemed_parcel_never_regenerated_end_to_end(tmp_path=None):
    """
    Real end-to-end regression: build a tiny fixture tree with the exact
    real shape of the two source CSVs (one redeemed parcel matching the
    real Gridley case, one clean parcel), monkeypatch regen_butte_dossiers
    and report_builder to write into a temp directory, run the actual
    main() entry point, and confirm the redeemed parcel produced NO
    dossier while the clean one did. This is the test that would have
    caught the original bug - before the fix, both would have been
    generated.
    """
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="butte_redemption_test_"))
    (tmp / "tax_pipeline").mkdir()
    (tmp / "butte").mkdir()
    out_dashboard = tmp / "output" / "dashboard"
    out_dashboard.mkdir(parents=True)

    # Minimal real-shaped auction-enriched CSV (tax_pipeline/butte_auction_all_105_enriched.csv)
    auction_fields = ["apn_dash", "pdf_owner", "owner_name", "min_bid", "score",
                       "net_assessed_value", "total_open_mortgages", "open_lien_types",
                       "has_assignment_of_rents", "notice_of_default_present",
                       "has_trustee_deed", "recorder_doc_count", "entity_type",
                       "max_bid_threshold", "bid_to_value_pct", "source"]
    auction_rows = [
        {"apn_dash": "022-210-078-000", "pdf_owner": "GRIDLEY BUSINESS TRUST", "owner_name": "GRIDLEY BUSINESS TRUST",
         "min_bid": "2459682.88", "score": "0", "net_assessed_value": "3832194", "total_open_mortgages": "1",
         "open_lien_types": "", "has_assignment_of_rents": "False", "notice_of_default_present": "False",
         "has_trustee_deed": "False", "recorder_doc_count": "1", "entity_type": "trust",
         "max_bid_threshold": "0", "bid_to_value_pct": "0%", "source": "NEWLY_ENRICHED"},
        {"apn_dash": "001-081-006-000", "pdf_owner": "CLEAN OWNER", "owner_name": "CLEAN OWNER",
         "min_bid": "5000", "score": "50", "net_assessed_value": "50000", "total_open_mortgages": "0",
         "open_lien_types": "", "has_assignment_of_rents": "False", "notice_of_default_present": "False",
         "has_trustee_deed": "False", "recorder_doc_count": "1", "entity_type": "individual",
         "max_bid_threshold": "12500", "bid_to_value_pct": "10%", "source": "NEWLY_ENRICHED"},
    ]
    with open(tmp / "tax_pipeline" / "butte_auction_all_105_enriched.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=auction_fields)
        w.writeheader()
        w.writerows(auction_rows)

    # Minimal real-shaped call sheet CSV (butte/butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv)
    # - only the fields regen_butte_dossiers.py and report_builder.py actually read.
    call_fields = ["apn", "verified_current_owner_name", "situs_address", "v_total_balance",
                   "net_taxable_value", "redemption_status", "redemption_date"]
    call_rows = [
        {"apn": "022-210-078-000", "verified_current_owner_name": "GRIDLEY BUSINESS TRUST",
         "situs_address": "177 DENIZ BROS LN GRIDLEY", "v_total_balance": "2459682.88",
         "net_taxable_value": "3832194", "redemption_status": "redeemed", "redemption_date": "2026-06-29"},
        {"apn": "001-081-006-000", "verified_current_owner_name": "CLEAN OWNER",
         "situs_address": "123 MAIN ST", "v_total_balance": "5000",
         "net_taxable_value": "50000", "redemption_status": "", "redemption_date": ""},
    ]
    with open(tmp / "butte" / "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=call_fields)
        w.writeheader()
        w.writerows(call_rows)

    orig_regen_root = regen_butte_dossiers.ROOT
    orig_output_dashboard = report_builder.OUTPUT_DASHBOARD
    orig_feed_file = report_builder.FEED_FILE
    try:
        regen_butte_dossiers.ROOT = tmp
        report_builder.OUTPUT_DASHBOARD = out_dashboard
        report_builder.FEED_FILE = out_dashboard / "dashboard_feed.json"

        regen_butte_dossiers.main()

        redeemed_dossier = out_dashboard / "butte_022210078000_prop_intel_dossier.md"
        clean_dossier = out_dashboard / "butte_001081006000_prop_intel_dossier.md"

        assert not redeemed_dossier.exists(), (
            "REGRESSION: a redeemed parcel (Gridley, 022-210-078-000) was regenerated as a "
            "dossier - the redemption filter is not actually connected to the generation path."
        )
        assert clean_dossier.exists(), "A clean, unredeemed parcel should still be generated normally."
    finally:
        regen_butte_dossiers.ROOT = orig_regen_root
        report_builder.OUTPUT_DASHBOARD = orig_output_dashboard
        report_builder.FEED_FILE = orig_feed_file

    print("PASS: redeemed parcel produces no dossier end-to-end; clean parcel still does")


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
