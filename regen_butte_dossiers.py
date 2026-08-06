"""
regen_butte_dossiers.py — One-off: regenerate Butte's prop-intel dossiers from the
two real, already-enriched local Butte datasets (not the live-fetch path in
fetch_butte_task1.py, which discards these columns and re-fetches live, mostly
failing and falling back to UNKNOWN/$0).

Sources merged on APN:
  - tax_pipeline/butte_auction_all_105_enriched.csv  (auction/lien/mortgage enrichment)
  - butte/butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv (ownership verification / mailing address)
"""
import csv
from pathlib import Path

import report_builder

ROOT = Path(__file__).resolve().parent


def norm_apn(a: str) -> str:
    return (a or "").replace("-", "").strip()


def load_auction_enriched():
    path = ROOT / "tax_pipeline" / "butte_auction_all_105_enriched.csv"
    with open(path, encoding="utf-8") as f:
        return {norm_apn(r["apn_dash"]): r for r in csv.DictReader(f)}


def load_call_sheet():
    path = ROOT / "butte" / "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"
    with open(path, encoding="utf-8") as f:
        return {norm_apn(r["apn"]): r for r in csv.DictReader(f)}


def main():
    auction = load_auction_enriched()
    verified = load_call_sheet()
    all_apns = sorted(set(auction) | set(verified))

    generated = 0
    for apn in all_apns:
        a = auction.get(apn, {})
        v = verified.get(apn, {})

        apn_dash = a.get("apn_dash") or v.get("apn") or apn
        owner = (v.get("verified_current_owner_name") or a.get("owner_name") or "").strip()
        assessed = a.get("net_assessed_value") or v.get("net_taxable_value")
        min_bid = a.get("min_bid") or v.get("v_total_balance")
        situs = v.get("situs_address") or a.get("address")
        doc_count = a.get("recorder_doc_count")
        notice_of_default = str(a.get("notice_of_default_present", "")).strip().lower() == "true"
        source_bits = []
        if a:
            source_bits.append("tax_pipeline/butte_auction_all_105_enriched.csv")
        if v:
            source_bits.append("butte/butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")

        parcel_data = {
            "apn_dash": apn_dash,
            "owner_name": owner or None,
            "net_assessed_value": assessed,
            "net_taxable_value": assessed,
            "min_bid": min_bid,
            "situs": situs,
            "recorder_doc_count": doc_count,
            "notice_of_default_present": notice_of_default,
            "owner_state": v.get("owner_state"),
            "out_of_state": v.get("out_of_state"),
            "source_file": " + ".join(source_bits),
            "verification_status": (
                f"PARTIALLY VERIFIED — owner_name_confidence={v.get('owner_name_confidence')}, "
                f"verification_score={v.get('verification_score')}"
                if v.get("verification_score") else None
            ),
        }

        report_builder.build_property_intelligence_dossier(parcel_data, "butte")
        generated += 1

    print(f"Regenerated {generated} Butte dossiers from real merged source data.")


if __name__ == "__main__":
    main()
