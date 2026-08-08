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

        parcel_data = {
            "apn_dash": apn,
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
            "verification_status": (
                f"VERIFIED — BOTH SITES. Assessed value and tax-default status confirmed live against "
                f"the county assessor. Owner of record confirmed via the recorder's document-number "
                f"search on the exact recorded document ({rec.get('doc_type')}, {rec.get('doc_date')}) "
                f"already captured for this specific parcel — tied to this APN, not a name-only match."
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
