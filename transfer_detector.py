#!/usr/bin/env python3
"""
Post-Stage 7 transfer detection.
Adds transfer_risk column: LOW / MEDIUM / HIGH / UNKNOWN.
"""
import re
import pandas as pd
from datetime import datetime


TRANSFER_DOC_TYPES = [
    "GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED",
    "CORPORATION GRANT DEED", "TRUST TRANSFER DEED",
    "DEED OF TRUST", "RECONVEYANCE", "FULL RECONVEYANCE"
]


def parse_date(s):
    if pd.isna(s) or str(s).lower() in ["nan", "none", ""]:
        return None
    try:
        return pd.to_datetime(str(s))
    except:
        return None


def normalize_name(name):
    if pd.isna(name):
        return ""
    return re.sub(r"[^\w]", "", str(name).upper())


def name_overlap(owner, other):
    """Check if owner name appears in another name string."""
    owner_clean = normalize_name(owner)
    other_clean = normalize_name(other)
    if not owner_clean or not other_clean:
        return False
    # Check last name overlap
    owner_tokens = set(re.findall(r"[A-Z]{2,}", owner_clean))
    other_tokens = set(re.findall(r"[A-Z]{2,}", other_clean))
    shared = owner_tokens & other_tokens
    return len(shared) >= 1 and len(owner_tokens) > 0


def assess_transfer_risk(row):
    score = 0
    reasons = []

    owner = str(row.get("assessee_name", row.get("owner_name", ""))).strip()
    status = str(row.get("ownership_status", "")).lower()

    # Signal 1: Stage 7 already flagged transfer
    if "sold" in status or "transfer" in status:
        return "HIGH", "Stage 7 flagged sold/transfer"

    # Signal 2: Recent deed date (2024+)
    doc_date = parse_date(row.get("rec_doc_date"))
    if doc_date and doc_date.year >= 2024:
        score += 3
        reasons.append(f"recent deed {doc_date.year}")

    # Signal 3: Most recent deed type is a transfer doc
    doc_num = str(row.get("rec_doc_number", "")).upper()
    if any(t in doc_num for t in TRANSFER_DOC_TYPES):
        score += 2
        reasons.append("transfer doc type")

    # Signal 4: Active reconveyance (loan paid off, often post-sale)
    if str(row.get("has_reconveyance", False)).lower() in ["true", "1", "yes"]:
        score += 2
        reasons.append("reconveyance recorded")

    # Signal 5: Name mismatch between tax owner and recorder name (if available)
    recorder_name = str(row.get("recorder_owner", "")).strip()
    if recorder_name and owner and not name_overlap(owner, recorder_name):
        score += 4
        reasons.append("recorder name mismatch")

    # Signal 6: Zero balance but delinquent status (often data lag after transfer)
    balance = 0.0
    try:
        balance = float(re.sub(r"[^\d.]", "", str(row.get("v_total_balance", 0))))
    except:
        pass
    if balance == 0 and str(row.get("v_delinquent", "")).lower() in ["true", "1", "yes"]:
        score += 2
        reasons.append("zero balance but delinquent")

    if score >= 4:
        return "HIGH", "; ".join(reasons) if reasons else "multiple transfer signals"
    elif score >= 2:
        return "MEDIUM", "; ".join(reasons) if reasons else "some transfer signals"
    elif reasons:
        return "LOW", "; ".join(reasons)
    return "LOW", "no transfer signals"


def main():
    df = pd.read_csv('all_seller_intent_HIGH.csv')
    results = df.apply(assess_transfer_risk, axis=1)
    df["transfer_risk"] = [r[0] for r in results]
    df["transfer_reasons"] = [r[1] for r in results]

    # Remove HIGH risk from sellable list
    sellable = df[df["transfer_risk"] != "HIGH"].copy()
    review = df[df["transfer_risk"] == "HIGH"].copy()

    print(f"Total HIGH intent: {len(df)}")
    print(f"Sellable (LOW/MEDIUM): {len(sellable)}")
    print(f"Needs review (HIGH): {len(review)}")
    print(f"\nRemoved HIGH risk leads:")
    print(review[['assessee_name', 'address', 'rec_doc_date', 'transfer_reasons']].head(20).to_string(index=False))

    sellable.to_csv('all_seller_intent_HIGH_sellable.csv', index=False)
    
    # Also update the sample clean leads
    try:
        # filter leads_for_sale.csv
        lfs = pd.read_csv('leads_for_sale.csv')
        # get apns of sellable leads
        sellable_apns = sellable['apn'].tolist()
        if 'fee_parcel' in sellable.columns:
            sellable_apns.extend(sellable['fee_parcel'].dropna().tolist())
        lfs_clean = lfs[lfs['APN'].isin(sellable_apns)]
        lfs_clean.head(5).to_csv('sample_5_clean_leads.csv', index=False)
    except Exception as e:
        print(f"Could not update sample clean leads: {e}")

    review.to_csv('transfer_review_queue.csv', index=False)

    print(f"\nSaved sellable list and sample.")


if __name__ == "__main__":
    main()
