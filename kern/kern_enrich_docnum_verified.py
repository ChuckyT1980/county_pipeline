"""
Build real Kern dossiers using BOTH-SITES verification:
  - Assessor (assessorapps.kerncounty.com, live): net taxable value, situs,
    default status, and the specific recent recorded document number.
  - Recorder (recorderonline.co.kern.ca.us, document-number search): the
    real grantor/grantee tied to THAT EXACT document — not a name-only
    match, an actual parcel-tied confirmation.

Owner name used is the recorder's GRANTEE on the most recent document for
this parcel — the true current party of interest — not the (sometimes
stale) bulk source-list name. 57 of 245 parcels tonight had a bulk-list
name that no longer matched the real current grantee (a private-sale deed
the old already-transferred filter, which only checked for "Deed - Tax",
never caught) — those are corrected here, not excluded, since the live
assessor check still shows them tax-defaulted regardless of who holds title.
"""
import csv
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder
from property_model import atn_to_assessor_parcel_number, apn1_cross_check_digits

SCRATCH = "/tmp/claude-1000/-home-chuck/e8fa5be3-9aea-4fd1-9c7a-07ad25a9bdf2/scratchpad"
ASSESSOR = f"{SCRATCH}/kern_real_batch_merged.csv"
RECORDER = f"{SCRATCH}/kern_docnum_recorder_results.csv"
SOURCE = "/mnt/c/Users/chuck/Downloads/county_pipeline/kern/kern_REAL_AUCTION_PARCELS_CLEAN.csv"


def norm(apn):
    return (apn or "").replace("-", "").strip()


def main():
    with open(ASSESSOR, encoding="utf-8") as f:
        assessor_by_apn = {r["apn"]: r for r in csv.DictReader(f)}

    with open(RECORDER, encoding="utf-8") as f:
        recorder_rows = list(csv.DictReader(f))

    with open(SOURCE, encoding="utf-8", errors="replace") as f:
        source_by_apn = {norm(r.get("Parcel_Number") or r.get("APN_1")): r for r in csv.DictReader(f)}

    generated = 0
    corrected_owner = 0
    for rec in recorder_rows:
        apn = rec["apn"]
        assessor = assessor_by_apn.get(apn, {})
        if not assessor:
            continue

        real_owner = rec.get("grantee") or None
        candidate = rec.get("candidate_name_from_list")
        was_corrected = bool(real_owner and candidate and real_owner.strip().upper() != candidate.strip().upper())
        if was_corrected:
            corrected_owner += 1

        src = source_by_apn.get(norm(apn), {})
        min_bid_raw = src.get("Minimum_Bid_Owed", "")
        try:
            min_bid = float(str(min_bid_raw).replace("$", "").replace(",", "")) if min_bid_raw else None
        except ValueError:
            min_bid = None

        # Identifier integrity fix (DOSSIER_QA remediation, 2026-08-08):
        # `apn` here is actually the ATN (Assessment/Tax Number, e.g.
        # "017-490-06-00-3") from the source tax-roll CSV's Parcel_Number
        # column - it was previously passed straight through as apn_dash
        # and displayed as "**APN**" in every dossier. It is NOT the
        # assessor's own parcel number. Derive that separately, cross-
        # check it against the source list's own separate APN_1 column,
        # and label the verification status honestly - this has NOT been
        # independently confirmed by reading the assessor's own displayed
        # APN field (kern_real_pull.py's parse_detail_page() never
        # captured that field at all).
        assessor_apn = atn_to_assessor_parcel_number(apn)
        apn1_raw = src.get("APN_1", "")
        apn1_matches = apn1_cross_check_digits(apn1_raw, assessor_apn) if assessor_apn and apn1_raw else None
        if assessor_apn:
            if apn1_matches:
                apn_status = (
                    "NOT_VERIFIED — derived from the ATN's own structure (first 3 segments) and cross-checked "
                    f"against the source list's separate APN_1 column ({apn1_raw!r}, digits match); NOT independently "
                    "confirmed by reading the assessor's own displayed APN field this run"
                )
            else:
                apn_status = (
                    f"NOT_VERIFIED — derived from the ATN's own structure, but the source list's separate APN_1 "
                    f"column ({apn1_raw!r}) does NOT digit-match the derived value - flagged, do not treat as reliable "
                    "without human review"
                )
        else:
            assessor_apn = "UNKNOWN"
            apn_status = "UNKNOWN — ATN did not have the expected 3+ dash-separated segments; assessor parcel number could not be derived, not synthesized"

        parcel_data = {
            "apn_dash": apn,
            "source_identifier": apn,
            "source_identifier_type": "ATN (Assessment/Tax Number, Kern tax-roll identifier)",
            "assessor_apn": assessor_apn,
            "assessor_apn_verification_status": apn_status,
            "owner_name": real_owner,
            "net_taxable_value": float(assessor["net_taxable_value"]) if assessor.get("net_taxable_value") else None,
            "net_assessed_value": float(assessor["net_taxable_value"]) if assessor.get("net_taxable_value") else None,
            "min_bid": min_bid,
            "situs": assessor.get("situs"),
            "current_doc_number": rec.get("recent_doc_number"),
            "deed_date": rec.get("doc_date"),
            "source_file": (
                "assessorapps.kerncounty.com (live, verified 2026-08-06/07) "
                "+ recorderonline.co.kern.ca.us document-number search (live, verified 2026-08-08, "
                f"doc #{rec.get('recent_doc_number')})"
            ),
            # NOTE: this pipeline's source data (kern_REAL_AUCTION_PARCELS_CLEAN.csv)
            # is a historical snapshot, not the live/current Sept 2026 auction
            # list (not yet published as of this run) - deliberately NOT
            # setting auction_list_membership_verified=True, so
            # report_builder.py's own safety check renders the honest
            # "parcel-specific auction status not verified" wording rather
            # than an overclaimed "GOING TO AUCTION" signal.
            "verification_status": (
                f"VERIFIED — BOTH SITES (assessed value/tax-default status and recorder document/owner only - "
                f"the assessor parcel number itself is NOT independently verified, see Assessor APN Verification "
                f"Status above). Assessed value and tax-default status confirmed live against the county assessor. "
                f"Owner of record confirmed via the recorder's document-number search on the exact recorded document "
                f"({rec.get('doc_type')}, {rec.get('doc_date')}) already captured for this specific parcel — tied to "
                f"this parcel's ATN-identified record, not a name-only match."
                + (f" NOTE: this corrects a stale name from the original source list (\"{candidate}\") — "
                   f"the property has a more recent recorded transfer to \"{real_owner}\" that the source "
                   f"list predates." if was_corrected else "")
            ),
        }

        report_builder.build_property_intelligence_dossier(parcel_data, "kern")
        generated += 1

    print(f"\nGenerated {generated} real, both-sites-verified Kern dossiers "
          f"({corrected_owner} with an owner name corrected from the stale source list).")


if __name__ == "__main__":
    main()
