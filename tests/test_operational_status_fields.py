"""
Tests for the Auction-Identity corrective implementation's typed
operational-status model: report_builder.py's OperationalStatus /
build_operational_status() / compute_priority_signal_display(), the Kern
production wiring in kern/kern_enrich_docnum_verified.py, the Lake
production wiring in lake/lake_generate_dossiers.py, and the Butte
pass-through/exclusion-outcome wiring in regen_butte_dossiers.py.

Every renderer call in this file uses a monkeypatched
report_builder.OUTPUT_DASHBOARD / report_builder.FEED_FILE pointing at a
tempfile.mkdtemp() directory - the exact technique already established in
tests/test_butte_redemption_filter.py - so nothing here ever touches the
real output/dashboard/ or the real 365-dossier corpus. All source-artifact
reads use synthetic temp fixtures, never the real kern_REAL_AUCTION_PARCELS_CLEAN.csv
or lake_lien_classification_ALL.json files. No dossier regeneration, no
network, no git changes.

Run: python3 tests/test_operational_status_fields.py
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import report_builder  # noqa: E402
import regen_butte_dossiers  # noqa: E402
import lake.lake_generate_dossiers as lake_generate_dossiers  # noqa: E402


class _TempOutput:
    """Monkeypatches report_builder.OUTPUT_DASHBOARD/FEED_FILE for the
    duration of a `with` block, restoring the real values afterward -
    same pattern as tests/test_butte_redemption_filter.py."""

    def __enter__(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="op_status_test_"))
        self.dashboard = self._tmp / "output" / "dashboard"
        self.dashboard.mkdir(parents=True)
        self._orig_dashboard = report_builder.OUTPUT_DASHBOARD
        self._orig_feed = report_builder.FEED_FILE
        report_builder.OUTPUT_DASHBOARD = self.dashboard
        report_builder.FEED_FILE = self.dashboard / "dashboard_feed.json"
        return self

    def __exit__(self, *exc):
        report_builder.OUTPUT_DASHBOARD = self._orig_dashboard
        report_builder.FEED_FILE = self._orig_feed
        shutil.rmtree(self._tmp, ignore_errors=True)


def _minimal_eligible_parcel_data(**overrides):
    base = {
        "apn_dash": "000-000-000-000",
        "owner_name": "EXAMPLE OWNER",
        "net_assessed_value": 100000.0,
        "net_taxable_value": 100000.0,
        "current_doc_number": "2026-000001",
    }
    base.update(overrides)
    return base


def _feed_entries(temp_output: _TempOutput):
    return json.loads(report_builder.FEED_FILE.read_text(encoding="utf-8"))


# ── 1. Kern: local Auction_ID match renders honestly, never as a live claim ──

def test_kern_local_auction_id_match_renders_correctly_never_live():
    parcel_data = _minimal_eligible_parcel_data(
        auction_listing_id="20569.0",
        auction_identity_status="locally_matched_not_live_reconfirmed",
        status_source_artifact_ref="kern/kern_REAL_AUCTION_PARCELS_CLEAN.csv:Parcel_Number=017-490-06-00-3",
        # auction_list_membership_verified deliberately absent - matches the
        # real kern_enrich_docnum_verified.py behavior exactly.
    )
    with _TempOutput() as t:
        out_file = report_builder.build_property_intelligence_dossier(parcel_data, "kern")
        text = out_file.read_text(encoding="utf-8")

        assert "20569.0" in text, "Auction_ID must render"
        assert "locally_matched_not_live_reconfirmed" in text
        assert "kern_REAL_AUCTION_PARCELS_CLEAN.csv:Parcel_Number=017-490-06-00-3" in text
        assert "retrieval_time_unknown" in text
        assert "AUCTION LIVE NOW" not in text
        assert "GOING TO AUCTION" not in text

        feed = _feed_entries(t)
        assert feed[0]["auction_listing_id"] == "20569.0"
        assert feed[0]["auction_identity_status"] == "locally_matched_not_live_reconfirmed"
        assert feed[0]["auction_list_membership_verified"] is False
        assert feed[0]["freshness_status"] == "retrieval_time_unknown"
    print("PASS: Kern local Auction_ID match renders identity/status/source-ref/freshness honestly, never as a live/current claim")


# ── 2. Butte: pass-through + exclusion visibility + no unconditional live claim ──

def test_butte_eligible_record_carries_literal_fields_through():
    auction_row = {"apn_dash": "001-081-006-000", "owner_name": "CLEAN OWNER", "net_assessed_value": "50000"}
    verified_row = {
        "apn": "001-081-006-000", "verified_current_owner_name": "CLEAN OWNER",
        "redemption_status": "", "redemption_date": "", "power_to_sell_date": "2025-01-01",
    }
    parcel_data, exclusion = regen_butte_dossiers.build_parcel_outcome("001-081-006-000", auction_row, verified_row)
    assert exclusion is None
    assert parcel_data is not None
    assert parcel_data["power_to_sell_date"] == "2025-01-01"
    assert parcel_data["redemption_status"] is None  # empty string -> None, not a blank that could be misread
    print("PASS: an eligible Butte record carries redemption_status/date and power_to_sell_date through literally")


def test_butte_redeemed_record_excluded_with_visible_reason():
    auction_row = {"apn_dash": "022-210-078-000", "owner_name": "GRIDLEY BUSINESS TRUST"}
    verified_row = {"apn": "022-210-078-000", "redemption_status": "redeemed", "redemption_date": "2026-06-29"}
    parcel_data, exclusion = regen_butte_dossiers.build_parcel_outcome("022-210-078-000", auction_row, verified_row)
    assert parcel_data is None, "a redeemed record must never produce a dossier"
    assert exclusion is not None
    assert exclusion["apn"] == "022-210-078-000"
    assert "redeemed" in exclusion["reconciliation_or_exclusion_reason"]
    assert exclusion["redemption_date"] == "2026-06-29"
    print("PASS: a redeemed Butte record is excluded and its literal exclusion reason/date are preserved in a structured outcome")


def test_no_unconditional_auction_live_now_path_remains():
    signal = {"signal_type": "AUCTION_LIVE", "priority_label": "AUCTION LIVE NOW (through 2026-08-10)"}

    # Neither condition met (the real, current Butte state - never set True from a local match).
    status_unconfirmed = report_builder.build_operational_status(
        {"auction_identity_status": "locally_matched_not_live_reconfirmed"}, county="butte", signal=signal,
    )
    display = report_builder.compute_priority_signal_display(
        signal=signal, status=status_unconfirmed, auction_list_membership_verified=False,
        window_display="2026-08-07 to 2026-08-10",
    )
    assert display == (
        "Tax-default / power-to-sell public-record indicator. A county-wide auction window is "
        "recorded as 2026-08-07 to 2026-08-10; this parcel's current official listing "
        "status has not been independently confirmed."
    ), display
    assert "AUCTION LIVE NOW" not in display

    # Both conditions genuinely met - the raw label IS allowed to render (proves the gate isn't permanently disabled).
    status_confirmed = report_builder.build_operational_status(
        {"auction_identity_status": "live_confirmed", "auction_list_membership_verified": True},
        county="butte", signal=signal,
    )
    display_confirmed = report_builder.compute_priority_signal_display(
        signal=signal, status=status_confirmed, auction_list_membership_verified=True,
        window_display="2026-08-07 to 2026-08-10",
    )
    assert display_confirmed == "AUCTION LIVE NOW (through 2026-08-10)"
    print("PASS: 'AUCTION LIVE NOW' only renders when both auction_list_membership_verified and auction_identity_status=='live_confirmed' are true; otherwise the exact required fallback wording renders")


# ── 3. Lake: structured status enum + deterministic document summary ──

def test_lake_document_summary_preserves_literal_fields_and_order():
    docs = [
        {"doc_number": "2026005658", "doc_type": "36 DEED TAX", "recording_date": "06/05/2026 09:16 AM",
         "grantor": "LAKE COUNTY TAX COLLECTOR", "grantee": "KAL CAPITAL PROPERTIES"},
        {"doc_number": "2025007916", "doc_type": "TAX DEFAULT PROPERTY LIEN", "recording_date": "08/14/2025 08:17 AM",
         "grantor": "LOPEZ IGNACIO", "grantee": "LAKE COUNTY TAX COLLECTOR"},
    ]
    summary = lake_generate_dossiers.build_document_summary(docs)
    assert summary == (
        "2026005658 (36 DEED TAX, recorded 06/05/2026 09:16 AM, grantor=LAKE COUNTY TAX COLLECTOR, "
        "grantee=KAL CAPITAL PROPERTIES); "
        "2025007916 (TAX DEFAULT PROPERTY LIEN, recorded 08/14/2025 08:17 AM, grantor=LOPEZ IGNACIO, "
        "grantee=LAKE COUNTY TAX COLLECTOR)"
    ), summary
    assert lake_generate_dossiers.build_document_summary([]) is None
    assert lake_generate_dossiers.build_document_summary(None) is None
    print("PASS: Lake's document summary preserves literal doc_number/type/date/grantor/grantee in exact source order")


def test_lake_lien_classification_load_is_real_production_wiring():
    """Exercises the actual production function against a synthetic temp
    JSON fixture (not a hand-simulated dict) - proves the real wiring
    works, not just renderer plumbing."""
    tmp = Path(tempfile.mkdtemp(prefix="lake_lien_test_"))
    try:
        fixture = tmp / "lake_lien_classification_ALL.json"
        fixture.write_text(json.dumps([
            {"apn": "002-023-380-000", "status": "STILL_DEFAULTED_NO_RELEASE_FOUND", "min_bid": "35000.00",
             "docs_json": [{"doc_number": "2025007916", "doc_type": "TAX DEFAULT PROPERTY LIEN",
                            "recording_date": "08/14/2025 08:17 AM", "grantor": "EXAMPLE OWNER",
                            "grantee": "LAKE COUNTY TAX COLLECTOR"}]},
        ]), encoding="utf-8")

        orig = lake_generate_dossiers.LIEN_CLASSIFICATION
        lake_generate_dossiers.LIEN_CLASSIFICATION = str(fixture)
        try:
            lien_by_apn = lake_generate_dossiers.load_lien_classification()
        finally:
            lake_generate_dossiers.LIEN_CLASSIFICATION = orig

        assert "002-023-380-000" in lien_by_apn
        assert lien_by_apn["002-023-380-000"]["status"] == "STILL_DEFAULTED_NO_RELEASE_FOUND"

        # Missing-file case must not raise - it's an enrichment, not a hard requirement.
        lake_generate_dossiers.LIEN_CLASSIFICATION = str(tmp / "does_not_exist.json")
        try:
            assert lake_generate_dossiers.load_lien_classification() == {}
        finally:
            lake_generate_dossiers.LIEN_CLASSIFICATION = orig
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS: load_lien_classification() (the real production function) reads a synthetic fixture correctly and fails soft (empty dict, no raise) when the file is missing")


def test_lake_status_and_summary_render_without_title_conclusion():
    parcel_data = _minimal_eligible_parcel_data(
        apn_dash="002-023-380-000",
        property_tax_status="STILL_DEFAULTED_NO_RELEASE_FOUND",
        source_document_summary=(
            "2025007916 (TAX DEFAULT PROPERTY LIEN, recorded 08/14/2025 08:17 AM, "
            "grantor=EXAMPLE OWNER, grantee=LAKE COUNTY TAX COLLECTOR)"
        ),
        status_source_artifact_ref="lake/lake_lien_classification_ALL.json:apn=002-023-380-000",
    )
    with _TempOutput() as t:
        out_file = report_builder.build_property_intelligence_dossier(parcel_data, "lake")
        text = out_file.read_text(encoding="utf-8")
        assert "STILL_DEFAULTED_NO_RELEASE_FOUND" in text
        assert "TAX DEFAULT PROPERTY LIEN" in text
        assert "lake/lake_lien_classification_ALL.json:apn=002-023-380-000" in text
        for forbidden in ("current owner is", "holds title", "legal owner", "lien priority is"):
            assert forbidden not in text.lower(), f"unsupported conclusion-style phrase found: {forbidden!r}"
    print("PASS: Lake's status enum and document summary render as literal structured facts, with no ownership/title/lien-priority conclusion")


# ── 4. County-wide timing never renders as an exact parcel deadline ──

def test_county_window_never_rendered_as_exact_deadline():
    signal_pre_auction = {"signal_type": "PRE_AUCTION_PRIORITY_1", "priority_label": "GOING TO AUCTION in 5 days"}
    display = report_builder.compute_priority_signal_display(
        signal=signal_pre_auction, status=report_builder.build_operational_status({}, county="kern", signal=signal_pre_auction),
        auction_list_membership_verified=False, window_display="2026-09-14 to 2026-09-16",
    )
    assert "county auction window confirmed 2026-09-14 to 2026-09-16" in display
    assert "GOING TO AUCTION" not in display

    status = report_builder.build_operational_status({}, county="kern", signal=signal_pre_auction)
    assert status.auction_timing_type == "county_window"

    no_schedule_signal = {"signal_type": "NO_SCHEDULED_AUCTION", "priority_label": "No scheduled auction — monitor for a future sale date"}
    status_unscheduled = report_builder.build_operational_status({}, county="lake", signal=no_schedule_signal)
    assert status_unscheduled.auction_timing_type == "unknown"
    assert status_unscheduled.auction_deadline is None
    print("PASS: county-wide windows always render as county-wide (auction_timing_type='county_window'), never as an exact parcel deadline; nothing in this system currently produces 'exact_deadline'")


# ── Typed-status invariant: live_confirmed requires the boolean True ──

def test_live_confirmed_without_membership_verified_is_safely_downgraded():
    signal = {"signal_type": "AUCTION_LIVE", "priority_label": "AUCTION LIVE NOW (through 2026-08-10)"}
    status = report_builder.build_operational_status(
        {"auction_identity_status": "live_confirmed"},  # membership boolean NOT supplied
        county="butte", signal=signal,
    )
    assert status.auction_identity_status == "unknown", (
        "live_confirmed must be safely downgraded to unknown when auction_list_membership_verified is not True"
    )
    print("PASS: a caller supplying auction_identity_status='live_confirmed' without auction_list_membership_verified=True is safely downgraded to 'unknown'")


def test_invalid_enum_values_default_to_unknown():
    signal = {"signal_type": "PRE_AUCTION_PRIORITY_1", "priority_label": "x"}
    status = report_builder.build_operational_status(
        {"auction_identity_status": "totally_made_up", "freshness_status": "also_made_up"},
        county="kern", signal=signal,
    )
    assert status.auction_identity_status == "unknown"
    assert status.freshness_status in ("unknown", "retrieval_time_unknown")
    print("PASS: an out-of-vocabulary auction_identity_status/freshness_status value defaults to 'unknown', never silently accepted")


# ── 5. Backward compatibility: callers without the new fields still work ──

def test_backward_compatible_caller_without_new_fields():
    parcel_data = _minimal_eligible_parcel_data()  # no operational-status fields at all
    with _TempOutput() as t:
        out_file = report_builder.build_property_intelligence_dossier(parcel_data, "lake")
        text = out_file.read_text(encoding="utf-8")
        assert "{{" not in text, "no unreplaced template placeholder may remain"
        assert "None available" in text  # auction_listing_id default
        assert "Unknown" in text  # property_tax_status default
        assert "retrieval_time_unknown" in text  # freshness default
        assert "Lien Risk Tier" not in text
    print("PASS: a caller supplying none of the new optional fields still renders successfully with honest unknown/unavailable defaults, no unreplaced placeholders, and no pre-existing evidence-integrity regression")


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
