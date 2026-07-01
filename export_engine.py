import pandas as pd
import sqlite3
import os
import numpy as np

def load_verified_status(db_path="tax_pipeline/cps1_outcomes.db"):
    """Load the latest Verification Status and Phone for each lead from the sqlite database."""
    if not os.path.exists(db_path):
        return pd.DataFrame(columns=["lead_id", "Verification Status", "best_phone"])
        
    conn = sqlite3.connect(db_path)
    try:
        # Get latest verification status per lead
        df_verif = pd.read_sql_query('''
            SELECT lead_id, verification_status as "Verification Status"
            FROM verification_events
            GROUP BY lead_id
            HAVING event_time = MAX(event_time)
        ''', conn)
    except sqlite3.OperationalError:
        df_verif = pd.DataFrame(columns=["lead_id", "Verification Status"])
        
    try:
        df_phone = pd.read_sql_query('''
            SELECT lead_id, best_phone
            FROM lead_contacts
            GROUP BY lead_id
            HAVING updated_at = MAX(updated_at)
        ''', conn)
    except sqlite3.OperationalError:
        df_phone = pd.DataFrame(columns=["lead_id", "best_phone"])
        
    conn.close()
    
    if df_verif.empty and df_phone.empty:
        return pd.DataFrame(columns=["lead_id", "Verification Status", "best_phone"])
        
    if df_verif.empty:
        df_verif = pd.DataFrame(columns=["lead_id", "Verification Status"])
    if df_phone.empty:
        df_phone = pd.DataFrame(columns=["lead_id", "best_phone"])
        
    df_merged = pd.merge(df_verif, df_phone, on="lead_id", how="outer")
    return df_merged


def generate_motivation_text(row):
    """Generate a human-readable reason for why the lead is being exported."""
    reasons = []
    if row.get("has_assignment_of_rents") == True:
        reasons.append("Distressed Landlord (Assignment of Rents)")
    if row.get("has_affidavit_of_death") == True:
        reasons.append("Probate / Estate (Affidavit of Death)")
    if row.get("is_corporate") == True:
        reasons.append("Corporate Entity")
    if row.get("is_trust") == True:
        reasons.append("Trust / Estate Ownership")
        
    if row.get("active_liens", 0) > 0:
        reasons.append(f"{int(row['active_liens'])} Active Lien(s)")
        
    if not reasons:
        return "No specific motivation flag"
    return " | ".join(reasons)


def run_crm_export(input_csv=None, output_csv="crm_ready_leads.csv", county="tehama"):
    if input_csv is None:
        input_csv = f"tax_pipeline/{county}_MASTER_leads_with_liens.csv"
    print(f"Loading master dataset: {input_csv}")
    if not os.path.exists(input_csv):
        print("Error: Input CSV not found.")
        return

    df = pd.read_csv(input_csv)
    
    # 1. Backfill and Generate Motivation Flags (Same logic as Dashboard)
    df["mailing_address"] = df.groupby("assessee_name")["mailing_address"].transform(lambda x: x.ffill().bfill())
    
    owner_upper = df["assessee_name"].fillna("").astype(str).str.upper()
    CORPORATE_MARKERS = ["LLC", "INC", "CORP", "CORPORATION", "HOLDINGS", "PROPERTIES", "COMPANY", "CO", "SERVICES", "ASSOCIATION", "PARTNERSHIP", "LP", "LLP"]
    corporate_pattern = r'\b(?:' + '|'.join(CORPORATE_MARKERS) + r')\b'
    df["is_corporate"] = owner_upper.str.contains(corporate_pattern, regex=True)
    
    TRUST_MARKERS = ["TRUST", "TR", "REVOC", "REVOCABLE", "ESTATE", "FAM", "FAMILY", "TESTAMENTARY", "LIVING", "IRREVOCABLE"]
    trust_pattern = r'\b(?:' + '|'.join(TRUST_MARKERS) + r')\b'
    df["is_trust"] = (~df["is_corporate"]) & owner_upper.str.contains(trust_pattern, regex=True)
    
    # Fill boolean flags if they don't exist yet from Stage 7
    for col in ["has_assignment_of_rents", "has_affidavit_of_death"]:
        if col not in df.columns:
            df[col] = False
        else:
            df[col] = df[col].fillna(False).astype(bool)
            
    for col in ["active_liens", "mortgages"]:
        if col not in df.columns:
            df[col] = 0
        else:
            df[col] = df[col].fillna(0).astype(int)
            
    df["ownership_status"] = df.get("ownership_status", pd.Series(["Current"] * len(df))).fillna("Current")
    
    # 2. Join Verification Data
    df_db = load_verified_status()
    raw_apn = df['apn_pdf'].fillna(df['fee_parcel']).astype(str).str.replace(r"\.0$", "", regex=True)
    def fmt_apn(a):
        import re
        digits = re.sub(r"\D", "", a)
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}" if len(digits) == 12 else a
    df['apn_fallback'] = raw_apn.apply(fmt_apn)
    prefix = county.capitalize() + "_"
    df['lead_id'] = prefix + df['apn_fallback'].astype(str)
    
    if not df_db.empty:
        # Drop any pre-existing columns to prevent merge suffix collision
        df = df.drop(columns=["Verification Status", "best_phone"], errors="ignore")
        df = pd.merge(df, df_db, on="lead_id", how="left")
    else:
        df["Verification Status"] = "Unverified"
        df["best_phone"] = ""
        
    if "Verification Status" not in df.columns:
        df["Verification Status"] = "Unverified"
    df["Verification Status"] = df["Verification Status"].fillna("Unverified")
    if "best_phone" not in df.columns:
        df["best_phone"] = ""
    df["best_phone"] = df["best_phone"].fillna("")
    
    # 3. Apply Export Rules & Tiers
    # Tier A: Manually marked Verified, not recently transferred, has motivation
    # Tier B: Passes rules but not manually verified
    # Tier C: Suppress (recent transfer or no motivation)
    
    df["motivation_reason_text"] = df.apply(generate_motivation_text, axis=1)
    
    has_meaningful_motivation = (
        (df["has_assignment_of_rents"] == True) | 
        (df["has_affidavit_of_death"] == True) | 
        (df["is_corporate"] == True) | 
        (df["is_trust"] == True) | 
        (df["active_liens"] > 0)
    )
    
    is_suppressed = (df["ownership_status"] != "Current") | (~has_meaningful_motivation)
    
    df["Export_Tier"] = "Tier C — Suppress"
    
    tier_a_mask = (df["Verification Status"] == "Verified") & (~is_suppressed)
    tier_b_mask = (df["Verification Status"] != "Verified") & (~is_suppressed)
    
    df.loc[tier_a_mask, "Export_Tier"] = "Tier A — Verified export"
    df.loc[tier_b_mask, "Export_Tier"] = "Tier B — Auto-review queue"
    
    # 4. Filter out Suppressed leads
    export_df = df[df["Export_Tier"] != "Tier C — Suppress"].copy()
    
    print(f"Total leads before filter: {len(df)}")
    print(f"Total leads after filter: {len(export_df)}")
    print(export_df["Export_Tier"].value_counts())
    
    if export_df.empty:
        print("No leads passed the export gate.")
        return
        
    # 5. Format CRM Output
    export_df["most_recent_deed_date"] = "" # Placeholder until extracted from Stage 7
    export_df["apn"] = export_df["apn_fallback"]
    
    # Secure address compilation (scrub empty strings so fillna works)
    situs_pdf_clean = export_df.get("situs_pdf", pd.Series([np.nan]*len(export_df))).replace({"": np.nan, "nan": np.nan, "NAN": np.nan, "None": np.nan})
    address_clean = export_df.get("address", pd.Series([np.nan]*len(export_df))).replace({"": np.nan, "nan": np.nan, "NAN": np.nan, "None": np.nan})
    export_df["property_address"] = situs_pdf_clean.fillna(address_clean).fillna("See Assessor")
    export_df["property_address"] = export_df["property_address"].astype(str).str.replace(r'(?i)\s+City\s*$', '', regex=True)
    
    crm_cols = [
        "apn",
        "assessee_name",
        "property_address",
        "mailing_address",
        "best_phone",
        "Export_Tier",
        "motivation_reason_text",
        "active_liens",
        "mortgages",
        "has_assignment_of_rents",
        "has_affidavit_of_death",
        "ownership_status",
        "most_recent_deed_date",
        "live_total_balance",
        "net_assessed_value",
        "Verification Status"
    ]
    
    # Ensure all cols exist
    for c in crm_cols:
        if c not in export_df.columns:
            export_df[c] = ""
            
    crm_output = export_df[crm_cols].sort_values(by="Export_Tier")
    
    crm_output.to_csv(output_csv, index=False)
    print(f"Export successful. Saved {len(crm_output)} leads to {output_csv}")

if __name__ == "__main__":
    run_crm_export()
