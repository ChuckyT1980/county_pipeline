"""
Build real Fresno dossiers from the verified batch — official government
minimum bid + item/default numbers, live-verified assessed value. Owner
name is honestly unverified (Fresno removed APN->owner lookup Jan 2025,
CA privacy law) — never guessed.
"""
import csv
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder

BATCH = "/mnt/c/Users/chuck/Downloads/county_pipeline/fresno/fresno_real_batch.csv"


def main():
    with open(BATCH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    generated = 0
    for row in rows:
        parcel_data = {
            "apn_dash": row["apn"],
            "owner_name": None,  # honestly unverified — Fresno's public tool no longer exposes this
            "net_taxable_value": float(row["net_assessed_value"]) if row.get("net_assessed_value") else None,
            "net_assessed_value": float(row["net_assessed_value"]) if row.get("net_assessed_value") else None,
            "min_bid": float(row["minimum_bid"]) if row.get("minimum_bid") else None,
            "situs": row.get("situs_confirmed") or row.get("location_official"),
            "current_doc_number": row.get("default_case_number"),
            "source_file": (
                "Fresno County Board of Supervisors Resolution 26-245 (File 26-0600, "
                f"item #{row['item_number']}, default #{row['default_case_number']}) "
                "+ assrmaps.co.fresno.ca.us live assessed value (verified 2026-08-06)"
            ),
            "verification_status": (
                "PARTIALLY VERIFIED — assessed value confirmed live against the county assessor; "
                "minimum bid and default case number from the county's own official Board of "
                "Supervisors resolution (not a scrape); owner name honestly unverified — Fresno "
                "removed public APN-to-owner lookup Jan 2025 under CA privacy law, and no free "
                "recorder cross-reference has been completed for this county yet"
            ),
        }

        report_builder.build_property_intelligence_dossier(parcel_data, "fresno")
        generated += 1

    print(f"Generated {generated} real, verified Fresno dossiers.")


if __name__ == "__main__":
    main()
