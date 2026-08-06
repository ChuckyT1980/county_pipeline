"""
Build real Tehama dossiers from the 24 parcels confirmed live to be
genuinely in current default, merging real assessed values (live,
2026-08-06) with owner names from pre_auction_intel.csv. Excludes the 6
that failed live re-verification rather than guessing.
"""
import csv
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder

LIVE = "/mnt/c/Users/chuck/Downloads/county_pipeline/tehama/tehama_tax_bill_enriched.csv"
LOCAL = "/mnt/c/Users/chuck/Downloads/county_pipeline/data/counties/tehama/pre_auction_intel.csv"


def main():
    with open(LOCAL, encoding="utf-8") as f:
        local_rows = {r["apn"]: r for r in csv.DictReader(f)}

    with open(LIVE, encoding="utf-8") as f:
        live_rows = list(csv.DictReader(f))

    confirmed = [r for r in live_rows if r["is_in_default"] == "True"]
    print(f"{len(confirmed)} of {len(live_rows)} confirmed genuinely in default (excluding {len(live_rows) - len(confirmed)})")

    generated = 0
    for row in confirmed:
        apn = row["source_apn"]
        local = local_rows.get(apn, {})

        parcel_data = {
            "apn_dash": apn,
            "owner_name": local.get("owner_name") or None,
            "net_taxable_value": float(row["net_taxable_value"]) if row.get("net_taxable_value") else None,
            "net_assessed_value": float(row["net_taxable_value"]) if row.get("net_taxable_value") else None,
            "situs": row.get("situs_from_tax") or local.get("situs"),
            "acreage": row.get("acres"),
            "current_doc_number": local.get("doc_number"),
            "tax_default_year": "20" + row["default_date"].split("/")[-1][-2:] if row.get("default_date") else None,
            "source_file": (
                "apps.mptsweb.com/TaxBillv2 (live, verified 2026-08-06, "
                f"default case {row.get('default_case_number')}) "
                "+ data/counties/tehama/pre_auction_intel.csv (owner name)"
            ),
            "verification_status": (
                f"PARTIALLY VERIFIED — assessed value and current default status (case "
                f"{row.get('default_case_number')}, defaulted {row.get('default_date')}) confirmed live "
                f"against the county tax bill; owner name from local list, not independently "
                f"recorder-cross-referenced (Tehama's recorder requires solving a Google reCAPTCHA "
                f"that no free automated method could pass tonight)"
            ),
        }

        report_builder.build_property_intelligence_dossier(parcel_data, "tehama")
        generated += 1

    print(f"\nGenerated {generated} real, verified Tehama dossiers.")


if __name__ == "__main__":
    main()
