import sqlite3
import pandas as pd
import os
import re
import subprocess
import sys

def clean_apn(val):
    if pd.isna(val): return ""
    return re.sub(r"[^0-9]", "", str(val)).zfill(12)

def clean_money(x):
    if pd.isna(x): return 0.0
    if isinstance(x, (int, float)): return float(x)
    s = str(x).replace('$', '').replace(',', '').strip()
    if not s or s.lower() in ('none', 'nan', 'null'): return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0

def main():
    base_dir = "C:/Users/chuck/Downloads/county_pipeline"
    db_path = os.path.join(base_dir, "data/counties/humboldt/state.sqlite")
    csv_path = os.path.join(base_dir, "data/counties/humboldt/excess_proceeds.csv")
    out_path = os.path.join(base_dir, "data/counties/humboldt/tax_deed_parcels.csv")
    
    # 1. Read excess_proceeds.csv first to get target APNs
    try:
        df_csv = pd.read_csv(csv_path, dtype=str)
    except FileNotFoundError:
        df_csv = pd.DataFrame()

    if not df_csv.empty and 'apn' in df_csv.columns:
        df_csv['apn_clean'] = df_csv['apn'].apply(clean_apn)
    else:
        df_csv['apn_clean'] = []

    csv_apn_list = list(set(df_csv['apn_clean'].dropna()))

    # 2. Query SQLite for tax_deed='yes' OR apn IN (excess_proceeds CSV APNs)
    conn = sqlite3.connect(db_path)
    
    placeholders = ','.join(['?'] * len(csv_apn_list)) if csv_apn_list else "''"
    query = f"""
        SELECT apn, owner, former_owner, [values], situs, current_doc_number, deed_date, tax_deed
        FROM parcels 
        WHERE tax_deed = 'yes' OR apn IN ({placeholders})
    """
    
    try:
        df_sqlite = pd.read_sql_query(query, conn, params=csv_apn_list)
    except Exception as e:
        query_fallback = f"SELECT * FROM parcels WHERE tax_deed = 'yes' OR apn IN ({placeholders})"
        df_sqlite = pd.read_sql_query(query_fallback, conn, params=csv_apn_list)
        
    conn.close()
    
    df_sqlite['apn_clean'] = df_sqlite['apn'].apply(clean_apn)

    # Prepare CSV data for merge
    if not df_csv.empty:
        cols_to_drop = [c for c in ['apn', 'apn_dash', 'situs'] if c in df_csv.columns]
        df_csv_merge = df_csv.drop(columns=cols_to_drop)
    else:
        df_csv_merge = pd.DataFrame(columns=['apn_clean', 'excess_proceeds', 'claim_deadline', 'auction_winner', 'deed_status'])

    # 3. Merge SQLite and CSV data
    df_merged = pd.merge(df_sqlite, df_csv_merge, on='apn_clean', how='outer')

    # Flag if in excess proceeds CSV
    df_merged['in_excess_csv'] = df_merged['apn_clean'].isin(set(csv_apn_list))
    
    # Rename [values] if present
    if '[values]' in df_merged.columns:
        df_merged = df_merged.rename(columns={'[values]': 'values'})
        
    # Standardize APN formatting to dash format if missing
    def format_dash_apn(apn_str):
        c = clean_apn(apn_str)
        if len(c) == 12:
            return f"{c[:3]}-{c[3:6]}-{c[6:9]}-{c[9:12]}"
        return apn_str

    df_merged['apn_dash'] = df_merged['apn_clean'].apply(format_dash_apn)

    out_cols = ['apn', 'apn_dash', 'owner', 'former_owner', 'values', 'situs', 'current_doc_number', 'deed_date',
                'excess_proceeds', 'claim_deadline', 'auction_winner', 'deed_status', 'in_excess_csv']

    for col in out_cols:
        if col not in df_merged.columns:
            df_merged[col] = None

    df_out = df_merged[out_cols].copy()

    # 4. Write output CSV
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df_out.to_csv(out_path, index=False)

    # 5. Calculate summary metrics
    has_excess = df_out[df_out['in_excess_csv'] == True].copy()
    num_has_excess = len(has_excess)
    
    has_excess['excess_num'] = has_excess['excess_proceeds'].apply(clean_money)
    total_amount = float(has_excess['excess_num'].sum()) if num_has_excess > 0 else 0.0

    if num_has_excess > 0 and 'claim_deadline' in has_excess.columns:
        deadlines = pd.to_datetime(has_excess['claim_deadline'], errors='coerce').dropna()
        if not deadlines.empty:
            deadline_min = deadlines.min().strftime('%Y-%m-%d')
            deadline_max = deadlines.max().strftime('%Y-%m-%d')
            deadline_range = f"{deadline_min} to {deadline_max}"
        else:
            deadline_range = "N/A"
    else:
        deadline_range = "N/A"

    print("=" * 65)
    print(" HUMBOLDT TAX DEED & EXCESS PROCEEDS EXTRACTION SUMMARY")
    print("=" * 65)
    print(f" Total Tax Deed / Excess Parcels Extracted : {len(df_out)}")
    print(f"  - Tax Deed = 'yes' in Assessor DB        : {len(df_sqlite[df_sqlite['tax_deed'] == 'yes'])}")
    print(f"  - Confirmed Excess Proceeds Parcels (CSV): {num_has_excess}")
    print(f" Total Excess Proceeds Dollar Amount       : ${total_amount:,.2f}")
    print(f" Claim Deadline Range                      : {deadline_range}")
    print(f" Output File Saved To                      : {out_path}")
    print("=" * 65)

    # Show Casey parcel details explicitly if present
    casey_rows = df_out[df_out['apn_dash'].str.contains('305-073-053', na=False) | df_out['owner'].str.contains('CASEY', na=False, case=False)]
    if not casey_rows.empty:
        print("\n--- CASEY PARCEL AUDIT VERIFICATION ---")
        for _, r in casey_rows.iterrows():
            print(f"  APN: {r['apn_dash']} | Owner: {r['owner']} | Excess: ${clean_money(r['excess_proceeds']):,.2f} | Deadline: {r['claim_deadline']} | Status: {r['deed_status']}")
        print("---------------------------------------")

    # 6. Resolve missing owners using owner_resolve.py
    missing_owner = df_out[df_out['owner'].isna() | (df_out['owner'] == '') | (df_out['owner'].astype(str).str.strip() == '')]
    if len(missing_owner) > 0:
        print(f"\nRunning owner_resolve.py for {len(missing_owner)} parcels with missing owner...")
        for apn_val in missing_owner['apn_dash']:
            print(f"--- Resolving {apn_val} ---")
            subprocess.run([sys.executable, "owner_resolve.py", str(apn_val), "humboldt"])

if __name__ == '__main__':
    main()
