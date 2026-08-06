"""
Post-enrichment score adjustments.

Applies fact-based rules to the priority_score AFTER all enrichment runs
have completed. Preserves raw_priority_score for provenance so we don't
lose the original scoring signal.

Rules applied:
    1. REDEEMED parcels -> priority_score = 0
       (delinquency cleared; parcel is off the auction. Detection fired in
       tax bill enricher; this rule makes the scorer respect it.)
    2. NO_OWNER + no situs + no distress -> priority_score capped at 50
       (little we can offer a buyer without any of the three anchor signals)
    3. Records the reason in priority_adjustment_reason

Idempotent: reads raw_priority_score if present so re-running doesn't
compound adjustments.
"""
import argparse
from pathlib import Path

import pandas as pd


def _blank(v):
    if v is None or pd.isna(v):
        return True
    return str(v).strip().lower() in {"", "nan", "none"}


def apply(csv_path: str) -> dict:
    df = pd.read_csv(csv_path, dtype=str)

    if "raw_priority_score" not in df.columns:
        df["raw_priority_score"] = df["priority_score"]
    if "priority_adjustment_reason" not in df.columns:
        df["priority_adjustment_reason"] = ""

    stats = {"redeemed_zeroed": 0, "no_owner_capped": 0, "total": len(df)}

    for idx, row in df.iterrows():
        raw_score = float(row.get("raw_priority_score") or row.get("priority_score") or 0)
        redemption = str(row.get("redemption_status", "")).strip().lower()
        owner = row.get("verified_current_owner_name")
        situs = row.get("situs_address")
        distress = float(pd.to_numeric(row.get("distress_signal_score"), errors="coerce") or 0)
        mail_ready = str(row.get("mail_ready_status", "")).strip().lower()

        new_score = raw_score
        reasons = []

        # Rule 1: redeemed -> 0
        if redemption == "redeemed":
            new_score = 0
            reasons.append("redeemed")
            stats["redeemed_zeroed"] += 1
        # Rule 2: mail_ready_status = "no" -> cap at 20 (bottom of pack)
        # This ensures no-owner / low-confidence parcels do NOT appear in top ranks.
        elif mail_ready == "no":
            if new_score > 20:
                new_score = 20
                reasons.append("mail_ready_no")
                stats["no_owner_capped"] = stats.get("no_owner_capped", 0) + 1
        # Rule 3: manual_review -> cap at 45 (below all mail_ready=yes)
        elif mail_ready == "manual_review":
            if new_score > 45:
                new_score = 45
                reasons.append("mail_ready_manual_review")
                stats["manual_review_capped"] = stats.get("manual_review_capped", 0) + 1
        # Rule 4: legacy no-anchor cap (preserved for records without mail_ready_status)
        elif _blank(owner) and _blank(situs) and distress == 0:
            if new_score > 50:
                new_score = 50
                reasons.append("no_owner_no_situs_no_distress")
                stats["no_owner_capped"] += 1

        df.at[idx, "priority_score"] = f"{new_score:.1f}"
        df.at[idx, "priority_adjustment_reason"] = "|".join(reasons)

    df.to_csv(csv_path, index=False)
    print(f"Applied score adjustments to {stats['total']} rows:")
    print(f"  Redeemed parcels zeroed:      {stats['redeemed_zeroed']}")
    print(f"  No-anchor parcels capped @50: {stats['no_owner_capped']}")
    return stats


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv_path")
    args = p.parse_args()
    apply(args.csv_path)
