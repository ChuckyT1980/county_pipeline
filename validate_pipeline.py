#!/usr/bin/env python3
"""
Validate county pipeline outputs.
"""
import pandas as pd
import glob
import os

COUNTIES = ["tehama", "shasta", "lassen", "butte"]

def validate(county):
    path = f"tax_pipeline/{county}_MASTER_leads_with_liens.csv"
    if not os.path.exists(path):
        print(f"[{county}] MISSING file")
        return False

    df = pd.read_csv(path)
    issues = []

    if len(df) == 0:
        issues.append("empty file")

    owner_col = "assessee_name" if "assessee_name" in df.columns else "owner_name"
    if owner_col not in df.columns:
        issues.append("no owner column")
    else:
        filled = df[owner_col].notna().sum()
        if filled < len(df) * 0.5:
            issues.append(f"owner names only {filled}/{len(df)}")

    if "live_total_balance" in df.columns:
        nonzero = (df["live_total_balance"].fillna(0) > 0).sum()
        if nonzero < len(df) * 0.5:
            issues.append(f"live balance only {nonzero}/{len(df)}")

    if "active_liens" not in df.columns:
        issues.append("no active_liens column")
    else:
        # Check if we have any liens at all
        if df["active_liens"].sum() == 0:
            issues.append("active_liens is 0 for EVERY lead (suspicious)")

    if issues:
        print(f"[{county}] ISSUES: {', '.join(issues)}")
        return False
    else:
        print(f"[{county}] OK — {len(df)} rows, owner filled, balances present")
        return True

print("=== Pipeline Validation ===\n")
for c in COUNTIES:
    validate(c)
