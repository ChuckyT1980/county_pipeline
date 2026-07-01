import pandas as pd
import numpy as np
import os
import zipfile

def generate_exports():
    input_file = "tax_pipeline/tehama_MASTER_leads_with_liens.csv"
    if not os.path.exists(input_file):
        print(f"Error: Could not find {input_file}. Please run the pipeline first.")
        return

    print("Loading Tehama master leads...")
    df = pd.read_csv(input_file)
    
    # Base setup
    df["County"] = "Tehama"
    df["Owner"] = df["assessee_name"].fillna("Unknown").astype(str)
    df["APN"] = df["apn_pdf"].fillna(df["fee_parcel"]).astype(str).str.replace(r"\.0$", "", regex=True)
    
    df["Balance_Val"] = pd.to_numeric(df["live_total_balance"], errors="coerce").fillna(0.0)
    df["Default Year"] = df["default_year"].fillna(df["earliest_year"]).fillna("Unknown")
    
    if "active_liens" not in df.columns:
        df["active_liens"] = 0
    if "mortgages" not in df.columns:
        df["mortgages"] = 0
        
    df["active_liens"] = df["active_liens"].fillna(0).astype(int)
    df["mortgages"] = df["mortgages"].fillna(0).astype(int)
    
    # Backfill missing mailing addresses for owners with multiple parcels
    df["mailing_address"] = df.groupby("assessee_name")["mailing_address"].transform(lambda x: x.ffill().bfill())
    
    # Motivation Signal (same logic as dashboard)
    mail = df["mailing_address"].fillna("").astype(str).str.upper()
    situs = df["situs_pdf"].fillna(df["address"]).fillna("").astype(str).str.upper()
    
    is_unknown = mail.str.strip() == ""
    is_ca = mail.str.contains(r'\bCA\b|CALIFORNIA', regex=True)
    
    COUNTY_CITIES = {
        "Tehama": ["RED BLUFF", "CORNING", "LOS MOLINOS", "TEHAMA", "VINA", "PASKENTA", "FLOURNOY", "PROBERTA", "GERBER", "MINERAL", "PAYNES CREEK", "MANTON"]
    }
    tehama_pattern = "|".join([fr"\b{c}\b" for c in COUNTY_CITIES["Tehama"]])
    is_local = mail.str.contains(tehama_pattern, regex=True)
    
    is_po_box = mail.str.contains(r'P\s*O\s*BOX|POST OFFICE BOX', regex=True)
    mail_num = mail.str.extract(r'^(\d+)')[0]
    situs_num = situs.str.extract(r'^(\d+)')[0]
    is_diff_street = (mail_num.notna()) & (situs_num.notna()) & (mail_num != situs_num)
    is_absentee = is_po_box | is_diff_street
    
    conditions = [is_unknown, ~is_ca, ~is_local, is_absentee]
    choices = [
        "Unknown",
        "High (Out-of-State)",
        "High (Non-Local CA)",
        "Medium (Local Absentee)"
    ]
    df["Motivation Signal"] = np.select(conditions, choices, default="Low (Owner Occupied)")

    # --- SCORE ENGINE ---
    score = np.zeros(len(df))
    
    # 1. Motivation
    score += np.where(df["Motivation Signal"] == "High (Out-of-State)", 25, 0)
    score += np.where(df["Motivation Signal"] == "High (Non-Local CA)", 15, 0)
    score += np.where(df["Motivation Signal"] == "Medium (Local Absentee)", 10, 0)
    
    # 2. Age
    current_year = 2026
    year_numeric = pd.to_numeric(df["Default Year"], errors='coerce').fillna(current_year)
    years_defaulted = np.where(df["Default Year"] != "Unknown", current_year - year_numeric, 0)
    
    score += np.where(years_defaulted >= 9, 15, 0)
    score += np.where((years_defaulted >= 7) & (years_defaulted < 9), 10, 0)
    score += np.where((years_defaulted >= 5) & (years_defaulted < 7), 5, 0)
    
    # 3. Balance
    balance_points = np.clip((df["Balance_Val"] / 5000.0) * 50.0, 0, 50)
    score += balance_points
    
    # 4. Lien Adjustment
    cond_free_clear = (df["active_liens"] == 0) & (df["mortgages"] == 0)
    cond_mortgage_only = (df["active_liens"] == 0) & (df["mortgages"] > 0)
    cond_one_lien = (df["active_liens"] == 1)
    cond_multi_lien = (df["active_liens"] > 1)
    
    lien_score = np.zeros(len(df))
    lien_score = np.where(cond_free_clear, 15, lien_score)
    lien_score = np.where(cond_mortgage_only, 5, lien_score)
    lien_score = np.where(cond_one_lien, -10, lien_score)
    lien_score = np.where(cond_multi_lien, -25, lien_score)
    
    score += lien_score
    
    if "ownership_status" not in df.columns:
        df["ownership_status"] = "Current"
    df["ownership_status"] = df["ownership_status"].fillna("Current")
    
    score = np.where(df["ownership_status"] == "Sold / Transfer Detected", 0, score)
    score = np.where(df["ownership_status"] == "Possible Transfer", score - 20, score)
    
    df["Opportunity_Score"] = score.astype(int)
    
    # --- TIERING ---
    # Tier 1 criteria: Score >= 50, Balance >= 1000, 0 active liens, current ownership
    tier1_cond = (df["Opportunity_Score"] >= 50) & (df["Balance_Val"] >= 1000) & (df["active_liens"] == 0) & (df["ownership_status"] == "Current")
    tier1_df = df[tier1_cond].copy()
    
    # Tier 2 criteria: Valid motivation/balance (Score >= 40 OR Balance >= $300), not in Tier 1, and NOT sold
    tier2_cond = ((df["Opportunity_Score"] >= 40) | (df["Balance_Val"] >= 300)) & ~tier1_cond & (df["ownership_status"] != "Sold / Transfer Detected")
    tier2_df = df[tier2_cond].copy()
    df["Tier"] = np.where(tier1_cond, 1, np.where(tier2_cond, 2, 3))
    
    # Filter to only Tier 1 and 2
    export_cols = [
        "APN", "Owner", "situs_pdf", "mailing_address", 
        "Default Year", "Balance_Val", "Opportunity_Score", "Tier",
        "Motivation Signal", "active_liens", "mortgages", "ownership_status"
    ]
    
    tier1_df = df[df["Tier"] == 1][export_cols].sort_values(by="Opportunity_Score", ascending=False)
    tier2_df = df[df["Tier"] == 2][export_cols].sort_values(by="Opportunity_Score", ascending=False)
    
    tier1_df.to_csv("tier1_export.csv", index=False)
    tier2_df.to_csv("tier2_export.csv", index=False)
    
    print(f"Generated tier1_export.csv ({len(tier1_df)} records)")
    print(f"Generated tier2_export.csv ({len(tier2_df)} records)")
    
    # Generate README.md
    readme_content = f"""# Tehama County Distressed Property Data Pack

## Overview
This dataset contains highly curated, probability-weighted liquidation opportunities in Tehama County. 
Instead of a raw list of thousands of noise records, these parcels have been processed through a 
structured ranking engine (CPS-1) to identify true distress, equity, and ownership clarity.

## What's Included

### Tier 1 (High-Intent Deal Sheet)
- **{len(tier1_df)} verified opportunities.**
- **Criteria:** Opportunity Score >= 50 AND Minimum Default Balance >= $1000 AND Title Clear (0 active liens).
- **Best for:** Immediate outreach, wholesaling, direct acquisition.

### Tier 2 (Structured Distressed Pipeline)
- **{len(tier2_df)} structured opportunities.**
- **Criteria:** Technically viable but more encumbered or lower balance.
- **Best for:** Consistent pipeline generation, multi-touch mailers.

## Data Dictionary
- **APN:** Assessor's Parcel Number
- **Owner:** Owner of Record
- **situs_pdf:** Property Address
- **mailing_address:** Mailing Address
- **Default Year:** Earliest recorded default year
- **Balance_Val:** Total Default Balance
- **Opportunity_Score:** 0-100+ Ranking Score
- **Tier:** 1 (High Intent) or 2 (Pipeline)
- **Motivation Signal:** Heuristic for absentee ownership
- **active_liens:** Count of active recorded liens (Title Risk)
- **mortgages:** Count of active mortgages/deeds of trust

---
*Generated by the Autonomous Intelligence Pipeline.*
"""
    with open("README.md", "w") as f:
        f.write(readme_content)
        
    print("Generated README.md")
    
    # Zip it up
    zip_filename = "county_pack_tehama.zip"
    with zipfile.ZipFile(zip_filename, 'w') as zipf:
        zipf.write("tier1_export.csv")
        zipf.write("tier2_export.csv")
        zipf.write("README.md")
        
    print(f"Packaged into {zip_filename}")

if __name__ == "__main__":
    generate_exports()
