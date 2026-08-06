"""
apply_master_backfill.py — Merges 12-APN manual backfill into Master CSV and regenerates Call Sheet + Sales/Equity layer
"""

import os
import pandas as pd
import json
from enrich_sales_equity import enrich_df_sales_equity

MASTER_CSV = os.path.join(os.path.dirname(__file__), "butte", "delivery", "butte_auction_2026-07-31", "butte_auction_intel_2026-07-31.csv")
CALL_SHEET_CSV = os.path.join(os.path.dirname(__file__), "butte", "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
BACKFILL_CSV = os.path.join(os.path.dirname(__file__), "butte_manual_backfill_12.csv")


def run_backfill():
    print(f"Loading backfill dataset from {BACKFILL_CSV}...")
    bf_df = pd.read_csv(BACKFILL_CSV, dtype=str)

    # Key backfill mapping by APN
    backfill_map = {}
    for _, row in bf_df.iterrows():
        apn = str(row["apn"]).strip()
        backfill_map[apn] = row.to_dict()

    print(f"Loading Master CSV from {MASTER_CSV}...")
    master_df = pd.read_csv(MASTER_CSV, dtype=str)

    # Ensure target columns exist in master_df
    target_cols = [
        "verified_current_owner_name", "situs_address", "owner_name_source",
        "owner_name_confidence", "owner_class", "estate_or_deceased",
        "deceased_owner", "excess_proceeds_candidate", "situs_source", "needs_review"
    ]
    for col in target_cols:
        if col not in master_df.columns:
            master_df[col] = ""

    updated_count = 0
    excess_candidate_count = 0

    for idx in master_df.index:
        apn = str(master_df.at[idx, "apn"]).strip()
        if apn in backfill_map:
            bf = backfill_map[apn]
            updated_count += 1

            if bf.get("verified_current_owner_name"):
                master_df.at[idx, "verified_current_owner_name"] = bf["verified_current_owner_name"]
            if bf.get("situs_address"):
                master_df.at[idx, "situs_address"] = bf["situs_address"]
            if bf.get("owner_name_source"):
                master_df.at[idx, "owner_name_source"] = bf["owner_name_source"]
            if bf.get("owner_name_confidence"):
                master_df.at[idx, "owner_name_confidence"] = bf["owner_name_confidence"]

            # Estate / Deceased & Excess Proceeds Candidate Flags
            is_estate_str = str(bf.get("estate_or_deceased", "")).lower()
            is_estate = is_estate_str in ("true", "1", "yes")
            master_df.at[idx, "estate_or_deceased"] = "true" if is_estate else "false"
            master_df.at[idx, "deceased_owner"] = "true" if is_estate else "false"

            is_excess_str = str(bf.get("excess_proceeds_candidate", "")).lower()
            is_excess = is_excess_str in ("true", "1", "yes")
            master_df.at[idx, "excess_proceeds_candidate"] = "true" if is_excess else "false"

            if is_excess:
                excess_candidate_count += 1

            if bf.get("situs_source"):
                master_df.at[idx, "situs_address_source"] = bf["situs_source"]
            if bf.get("needs_review"):
                master_df.at[idx, "needs_review"] = bf["needs_review"]

    print(f"Updated {updated_count} APNs in Master CSV from backfill file.")
    print(f"Explicitly flagged {excess_candidate_count} estate parcels as excess_proceeds_candidate=True.")

    # Save backfilled master CSV
    master_df.to_csv(MASTER_CSV, index=False)
    print(f"Saved updated Master CSV to {MASTER_CSV}")

    # Re-run Sales & Equity Layer (v1) over the updated Master CSV
    print("\nRe-running Sales & Equity Layer over Master CSV...")
    enriched_master = enrich_df_sales_equity(master_df, county="butte")
    enriched_master.to_csv(MASTER_CSV, index=False)

    # Regenerate Call Sheet as a clean projection of Master CSV
    print(f"Regenerating Call Sheet ({CALL_SHEET_CSV}) from Master CSV...")
    enriched_master.to_csv(CALL_SHEET_CSV, index=False)
    print("Regeneration complete.")

    # Verification Audit
    print("\n" + "=" * 60)
    print("BACKFILL VERIFICATION AUDIT:")
    print("=" * 60)
    print(f"Total Master Records: {len(enriched_master)}")

    excess_cands = enriched_master[enriched_master["excess_proceeds_candidate"] == True]
    print(f"Excess Proceeds Candidates: {len(excess_cands)}")
    print(f"   (APNs: {excess_cands['apn'].tolist()})")

    gate_counts = enriched_master["equity_gate_status"].value_counts().to_dict()
    print(f"Equity Gate Status Breakdown: {gate_counts}")

    conf_counts = enriched_master["equity_confidence"].value_counts().to_dict()
    print(f"Equity Confidence Breakdown: {conf_counts}")

    src_counts = enriched_master["market_estimate_source"].value_counts().to_dict()
    print(f"Market Estimate Source Breakdown: {src_counts}")

    band_counts = enriched_master["equity_band"].value_counts().to_dict()
    print(f"Equity Band Breakdown: {band_counts}")

    print("\n--- SPOT-CHECK TENURE-DERIVED EQUITY BANDS (§4b Audit & Buyer-Facing Note) ---")
    tenure_parcels = enriched_master[enriched_master["equity_band"].isin(["tenure_mid", "tenure_long"])].head(3)
    for idx, r in tenure_parcels.iterrows():
        print(f"APN: {r['apn']} | Owner: {r.get('verified_current_owner_name', '')}")
        print(f"   sale_price_proxy_assessor: {r.get('sale_price_proxy_assessor')} | market_estimate: {r.get('market_estimate')} ({r.get('market_estimate_source')})")
        print(f"   tenure_years: {r.get('tenure_years')} | equity_band: {r.get('equity_band')} | equity_confidence: {r.get('equity_confidence')}")
        buyer_note = f"owned {r.get('tenure_years')} yrs — equity likely, unverified"
        print(f"   -> Buyer-facing display: '{buyer_note}' (no unbacked dollar claim made)\n")


if __name__ == "__main__":
    run_backfill()
