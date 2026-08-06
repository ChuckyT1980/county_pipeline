"""
AI Seller Intent Scoring — runs after Stage 4/7 enrichment.

Usage:
    python run_ai_intent.py tehama
    python run_ai_intent.py tehama --input-csv tehama_MASTER_leads_with_liens.csv
    python run_ai_intent.py tehama --tier-filter HOT   (only score HOT leads)

Output:
    {county}_MASTER_ai_scored.csv  — all fields + AI columns
    {county}_MASTER_pre_empt.csv   — only pre_empt_candidate=True leads, sorted by urgency
"""

import sys, os, time, json
import pandas as pd
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("county")
    parser.add_argument("--input-csv", default=None)
    parser.add_argument("--tier-filter", default=None, help="Only score leads with verified_score=HOT (or WARM)")
    parser.add_argument("--max-rows", type=int, default=None, help="Cap for testing")
    args = parser.parse_args()

    base = os.path.dirname(os.path.abspath(__file__))
    input_csv = args.input_csv or os.path.join(base, f"{args.county}_MASTER_leads_with_liens.csv")
    
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found. Run stages 1-7 first.")
        sys.exit(1)

    df = pd.read_csv(input_csv)
    
    if args.tier_filter:
        df = df[df.get("verified_score", "").str.upper() == args.tier_filter.upper()]
        print(f"Filtered to {len(df)} {args.tier_filter} leads.")
    
    if args.max_rows:
        df = df.head(args.max_rows)

    from ai_seller_intent import SellerIntentAdjudicator, build_evidence_packet

    adj = SellerIntentAdjudicator()
    
    # Add AI output columns
    ai_cols = ["intent_score", "intent_tier", "motivation_narrative", "owner_profile_type",
               "contact_strategy", "letter_tone", "risk_flags", "best_offer_range_low",
               "best_offer_range_high", "time_sensitivity", "pre_empt_candidate", "ai_confidence"]
    for col in ai_cols:
        if col not in df.columns:
            df[col] = None

    print(f"\n[AI Intent] Scoring {len(df)} leads for {args.county.upper()}...")

    for i, row in df.iterrows():
        # Skip already scored
        if pd.notna(df.at[i, "intent_score"]) and df.at[i, "intent_score"] != 0:
            continue

        print(f"  [{i+1}/{len(df)}] {row.get('assessee_name', row.get('owner_name', 'UNKNOWN'))} | "
              f"APN: {row.get('asmt', '')} ...", end=" ", flush=True)

        packet = build_evidence_packet(row.to_dict())
        result = adj.score(packet)

        df.at[i, "intent_score"] = result.intent_score
        df.at[i, "intent_tier"] = result.intent_tier
        df.at[i, "motivation_narrative"] = result.motivation_narrative
        df.at[i, "owner_profile_type"] = result.owner_profile_type
        df.at[i, "contact_strategy"] = result.contact_strategy
        df.at[i, "letter_tone"] = result.letter_tone
        df.at[i, "risk_flags"] = json.dumps(result.risk_flags)
        df.at[i, "best_offer_range_low"] = result.best_offer_range_low
        df.at[i, "best_offer_range_high"] = result.best_offer_range_high
        df.at[i, "time_sensitivity"] = result.time_sensitivity
        df.at[i, "pre_empt_candidate"] = result.pre_empt_candidate
        df.at[i, "ai_confidence"] = result.confidence

        print(f"{result.intent_tier} ({result.intent_score}) — {result.motivation_narrative[:60]}...")

        # Save every 10 rows
        if (i + 1) % 10 == 0:
            df.to_csv(input_csv.replace(".csv", "_ai_scored.csv"), index=False)
        
        time.sleep(4.5)  # Gemini free tier limit is 15 RPM for certain models

    out_all = input_csv.replace(".csv", "_ai_scored.csv")
    df.to_csv(out_all, index=False)
    print(f"\n[OK] Full AI-scored output: {out_all}")

    # Pre-empt shortlist
    pre_empt = df[df["pre_empt_candidate"] == True].copy()
    pre_empt = pre_empt.sort_values("intent_score", ascending=False)
    out_pe = input_csv.replace(".csv", "_pre_empt.csv")
    pre_empt.to_csv(out_pe, index=False)
    print(f"[OK] Pre-empt candidates: {out_pe}  ({len(pre_empt)} leads)")

if __name__ == "__main__":
    main()
