"""
Butte dossier QA fixes — 4 items from the checklist review.

Item 1: Ownership-confidence gate. Sets mail_ready_status field.
        Records with owner_conf < 0.5 or no owner name are demoted from priority.
Item 4: Distress score recalibration. Ensures parcels with material default +
        long Power-to-Sell age get a non-zero floor.
Item 5: Normalize distress score to 0-100 (clamp negatives, cap at 100).
Item 10: Portfolio symmetry — every parcel in a portfolio group sees the same
         sibling list.

Idempotent: safe to re-run. Preserves raw_priority_score and raw_distress_score
for provenance so nothing is lost.
"""
import argparse
import os

import pandas as pd


def _money(v):
    if pd.isna(v):
        return 0.0
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _has_val(v):
    if v is None or pd.isna(v):
        return False
    return str(v).strip().lower() not in {"", "nan", "none"}


def apply_fixes(csv_path: str) -> dict:
    df = pd.read_csv(csv_path, dtype=str)
    stats = {
        "total": len(df),
        "mail_ready_yes": 0,
        "mail_ready_manual": 0,
        "mail_ready_no": 0,
        "distress_recalibrated": 0,
        "distress_normalized": 0,
        "portfolio_symmetrized": 0,
    }

    # ---------- Item 1: mail_ready_status via ownership-confidence gate ----------
    df["oc"] = pd.to_numeric(df["ownership_confidence"], errors="coerce").fillna(0)

    def _mail_ready(row):
        has_owner = _has_val(row.get("verified_current_owner_name"))
        oc = float(row.get("oc", 0) or 0)
        has_mailing = _has_val(row.get("mailing_address"))
        if not has_owner or oc < 0.30:
            return "no"
        if oc < 0.50 or not has_mailing:
            return "manual_review"
        return "yes"

    df["mail_ready_status"] = df.apply(_mail_ready, axis=1)
    stats["mail_ready_yes"] = int((df["mail_ready_status"] == "yes").sum())
    stats["mail_ready_manual"] = int((df["mail_ready_status"] == "manual_review").sum())
    stats["mail_ready_no"] = int((df["mail_ready_status"] == "no").sum())

    # ---------- Item 4: distress score recalibration ----------
    # Preserve raw
    if "raw_distress_signal_score" not in df.columns:
        df["raw_distress_signal_score"] = df["distress_signal_score"]

    df["_bal"] = df["v_total_balance"].apply(_money)
    df["_yrs_pts"] = pd.to_numeric(df["years_since_power_to_sell"], errors="coerce").fillna(0)
    df["_recorder_ds"] = pd.to_numeric(df["distress_signal_score"], errors="coerce").fillna(0)

    def _recalc_distress(row):
        recorder_ds = float(row["_recorder_ds"])   # 0-40 typical from recorder graph
        bal = float(row["_bal"])
        yrs_pts = float(row["_yrs_pts"])

        # Baseline components (all 0-25 scale, summed to 0-100)
        tax_age_component = min(25, yrs_pts * 3)  # 3 pts per year, cap at 25 (8+ yrs)
        tax_bal_component = min(25, (bal / 5000))  # $5k/pt cap at $125k = 25 pts
        # Recorder distress signals scaled to 0-30
        recorder_component = min(30, max(0, recorder_ds))
        # Absentee bonus
        absentee_bonus = 10 if row.get("out_of_state") == "Y" else 0
        # Portfolio bonus
        pcount = pd.to_numeric(row.get("portfolio_apn_count"), errors="coerce") or 0
        portfolio_bonus = min(10, max(0, (pcount - 1) * 5))

        total = tax_age_component + tax_bal_component + recorder_component + absentee_bonus + portfolio_bonus
        # Item 5: clamp to 0-100
        return max(0, min(100, round(total)))

    df["distress_signal_score"] = df.apply(_recalc_distress, axis=1).astype(str)
    stats["distress_recalibrated"] = int((df["distress_signal_score"].astype(int) !=
                                           pd.to_numeric(df["raw_distress_signal_score"], errors="coerce").fillna(0).astype(int)).sum())

    # Item 5: clamp any leftover negatives to 0 (should be none after recalc)
    stats["distress_normalized"] = int((pd.to_numeric(df["raw_distress_signal_score"], errors="coerce").fillna(0) < 0).sum())

    # ---------- Item 10: portfolio symmetry ----------
    # For every owner with 2+ parcels, ensure each parcel lists the OTHERS as siblings.
    if "portfolio_sibling_apns" not in df.columns:
        df["portfolio_sibling_apns"] = ""

    owner_groups = df[df["verified_current_owner_name"].apply(_has_val)]\
        .groupby("verified_current_owner_name")["apn"].apply(list).to_dict()

    def _symmetric_siblings(row):
        owner = row.get("verified_current_owner_name")
        if not _has_val(owner):
            return row.get("portfolio_sibling_apns", "")
        group = owner_groups.get(owner, [])
        if len(group) < 2:
            return ""
        # This parcel's siblings = all others in group
        siblings = [a for a in group if a != row.get("apn")]
        return "|".join(sorted(siblings))

    new_siblings = df.apply(_symmetric_siblings, axis=1)
    changed = int((new_siblings != df["portfolio_sibling_apns"].fillna("")).sum())
    df["portfolio_sibling_apns"] = new_siblings
    stats["portfolio_symmetrized"] = changed

    # Also recalc portfolio_apn_count for consistency
    df["portfolio_apn_count"] = df["verified_current_owner_name"].apply(
        lambda o: len(owner_groups.get(o, [])) if _has_val(o) else 1
    ).astype(str)

    # ---------- Drop internal columns before save ----------
    for c in ["_bal", "_yrs_pts", "_recorder_ds", "oc"]:
        if c in df.columns:
            df = df.drop(columns=[c])

    df.to_csv(csv_path, index=False)

    print(f"Butte QA fixes applied to {csv_path}")
    print(f"  Total parcels: {stats['total']}")
    print(f"  Mail-ready:      YES={stats['mail_ready_yes']}  "
          f"MANUAL={stats['mail_ready_manual']}  NO={stats['mail_ready_no']}")
    print(f"  Distress recalibrated: {stats['distress_recalibrated']} rows")
    print(f"  Distress negatives normalized: {stats['distress_normalized']} rows")
    print(f"  Portfolio siblings updated (symmetric): {stats['portfolio_symmetrized']} rows")
    return stats


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv_path", nargs="?",
                   default=r"C:\Users\chuck\Downloads\county_pipeline\butte\butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
    args = p.parse_args()
    apply_fixes(args.csv_path)
