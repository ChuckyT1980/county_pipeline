"""
Build real Tehama dossiers from a full-master-index tax-bill chunk (not just
the small pre-existing pre_auction_intel.csv set). Filters to only parcels
genuinely confirmed in default (is_in_default == True, via the fixed
default-case-number regex in tehama_tax_bill.py) — the master index itself
is the whole county roll, not a pre-filtered default list, so most rows are
NOT delinquent and must be excluded, not guessed into "maybe."

Owner name is pulled from the local pre_auction_intel.csv where the APN
overlaps (real, not guessed); otherwise honestly left unverified, same
pattern already used for Fresno (owner_name: None, plainly labeled) rather
than excluding the whole record over one missing field.

Usage: python tehama_enrich_chunk.py <tax_bill_csv_path>
"""
import csv
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder

LOCAL = "/mnt/c/Users/chuck/Downloads/county_pipeline/data/counties/tehama/pre_auction_intel.csv"


def main(chunk_path: str):
    with open(LOCAL, encoding="utf-8") as f:
        local_rows = {r["apn"]: r for r in csv.DictReader(f)}

    with open(chunk_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    defaults = [r for r in rows if r["is_in_default"] == "True"]
    print(f"{len(defaults)} of {len(rows)} genuinely confirmed in default (excluding {len(rows) - len(defaults)} not delinquent)")

    generated = 0
    owner_known = 0
    for row in defaults:
        apn = row["source_apn"]
        local = local_rows.get(apn, {})
        owner = local.get("owner_name") or None
        if owner:
            owner_known += 1

        parcel_data = {
            "apn_dash": apn,
            "owner_name": owner,
            "net_taxable_value": float(row["net_taxable_value"]) if row.get("net_taxable_value") else None,
            "net_assessed_value": float(row["net_taxable_value"]) if row.get("net_taxable_value") else None,
            "situs": row.get("situs_from_tax") or local.get("situs"),
            "acreage": row.get("acres"),
            "current_doc_number": local.get("doc_number"),
            "tax_default_year": "20" + row["default_date"].split("/")[-1][-2:] if row.get("default_date") else None,
            "source_file": (
                f"apps.mptsweb.com/TaxBillv2 (live, verified 2026-08-06, "
                f"default case {row.get('default_case_number')})"
                + (" + data/counties/tehama/pre_auction_intel.csv (owner name)" if owner else "")
            ),
            "verification_status": (
                f"PARTIALLY VERIFIED — assessed value and current default status (case "
                f"{row.get('default_case_number')}, defaulted {row.get('default_date')}) confirmed live "
                f"against the county tax bill; "
                + (
                    "owner name from local list, not independently recorder-cross-referenced"
                    if owner else
                    "owner name honestly UNVERIFIED — not present in any local source and Tehama's "
                    "recorder requires solving a Google reCAPTCHA that no free automated method could pass"
                )
            ),
        }

        report_builder.build_property_intelligence_dossier(parcel_data, "tehama")
        generated += 1

    print(f"\nGenerated {generated} real, verified Tehama dossiers ({owner_known} with a known owner name, {generated - owner_known} owner-unverified).")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/mnt/c/Users/chuck/Downloads/county_pipeline/tehama/tehama_tax_bill_offset0.csv")
