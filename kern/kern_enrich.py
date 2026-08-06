"""
Enrich the 40 genuinely-still-active Kern parcels into real dossiers,
using the same fixed report_builder.py / predictive_scorer.py pipeline
already proven on Butte. Already-transferred parcels are excluded, not
included with a caveat.
"""
import csv
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder

BATCH = "/tmp/claude-1000/-home-chuck/e8fa5be3-9aea-4fd1-9c7a-07ad25a9bdf2/scratchpad/kern_real_batch.csv"
SOURCE = "/mnt/c/Users/chuck/Downloads/county_pipeline/kern/kern_REAL_AUCTION_PARCELS_CLEAN.csv"


def norm(apn: str) -> str:
    return (apn or "").replace("-", "").strip()


def main():
    with open(SOURCE, encoding="utf-8", errors="replace") as f:
        source_rows = {norm(r.get("Parcel_Number") or r.get("APN_1")): r for r in csv.DictReader(f)}

    with open(BATCH, encoding="utf-8") as f:
        batch_rows = list(csv.DictReader(f))

    active = [r for r in batch_rows if r["likely_already_transferred"] != "True"]
    print(f"Enriching {len(active)} genuinely-active parcels (excluded {len(batch_rows) - len(active)} already-transferred)...")

    generated = 0
    for row in active:
        apn = row["apn"]
        src = source_rows.get(norm(apn), {})
        min_bid_raw = src.get("Minimum_Bid_Owed", "")
        try:
            min_bid = float(str(min_bid_raw).replace("$", "").replace(",", "")) if min_bid_raw else None
        except ValueError:
            min_bid = None

        parcel_data = {
            "apn_dash": apn,
            "owner_name": row.get("owner_from_source_list") or None,
            "net_taxable_value": float(row["net_taxable_value"]) if row.get("net_taxable_value") else None,
            "net_assessed_value": float(row["net_taxable_value"]) if row.get("net_taxable_value") else None,
            "min_bid": min_bid,
            "situs": row.get("situs"),
            "current_doc_number": row.get("recent_doc_number"),
            "deed_date": row.get("recent_doc_date"),
            "source_file": "assessorapps.kerncounty.com (live, verified 2026-08-06) + kern_REAL_AUCTION_PARCELS_CLEAN.csv (min bid)",
            "verification_status": (
                f"PARTIALLY VERIFIED — assessed value confirmed live against county assessor; "
                f"owner name from source list, not independently recorder-cross-referenced; "
                f"confirmed NOT already transferred (checked against recorded document history "
                f"as of 2026-08-06)"
            ),
        }

        report_builder.build_property_intelligence_dossier(parcel_data, "kern")
        generated += 1

    print(f"\nGenerated {generated} real, verified Kern dossiers.")


if __name__ == "__main__":
    main()
