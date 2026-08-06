"""
Assessment Roll Join Script
When a county sends back their CPRA assessment roll data,
drop the file in county_pipeline/<county>/ and run this script.
It will match APNs to your auction parcels and replace estimated
values with real verified assessor values, then re-export the workbook.

Usage:
  python tax_pipeline/join_assessor_roll.py --county kern --roll kern/assessor_roll_kern_2026.csv
  python tax_pipeline/join_assessor_roll.py --county fresno --roll fresno/assessor_roll_fresno_2026.xlsx
"""
import os, sys, re, argparse
import pandas as pd
import openpyxl
from datetime import datetime

BASE = r"C:\Users\chuck\Downloads\county_pipeline"

COUNTY_CONFIG = {
    "kern":       {"call_sheet": "kern/kern_SCORED_AUCTION_MATCHES_CALL_SHEET.csv",
                   "workbook":   "kern/Kern_Auction_Intel_Workbook_REAL.xlsx"},
    "fresno":     {"call_sheet": "fresno/fresno_SCORED_AUCTION_MATCHES_CALL_SHEET.csv",
                   "workbook":   "fresno/Fresno_Auction_Intel_Workbook_REAL.xlsx"},
    "butte":      {"call_sheet": "butte/butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv",
                   "workbook":   "butte/Butte_Auction_Intel_Workbook_REAL.xlsx"},
    "shasta":     {"call_sheet": "shasta/shasta_AUTHORITATIVE_master_index.csv",
                   "workbook":   "shasta/Shasta_Auction_Intel_Workbook.xlsx"},
    "tehama":     {"call_sheet": "tehama/tehama_AUTHORITATIVE_master_index.csv",
                   "workbook":   "tehama/Tehama_Auction_Intel_Workbook.xlsx"},
}

def normalize_apn(apn):
    """Strip all non-digit characters for fuzzy matching."""
    return re.sub(r'\D', '', str(apn))

def find_apn_col(df):
    """Find the APN column in the assessor roll — counties name it differently."""
    for col in df.columns:
        cl = col.lower()
        if any(k in cl for k in ['apn','parcel_number','parcel number','assessor','ain']):
            return col
    return None

def find_value_cols(df):
    """Find land value, improvement value, total value columns."""
    land_col, impr_col, total_col = None, None, None
    for col in df.columns:
        cl = col.lower()
        if ('land' in cl) and ('value' in cl or 'val' in cl): land_col = col
        if any(k in cl for k in ['improvement','impr','building','struct']) and ('value' in cl or 'val' in cl): impr_col = col
        if ('total' in cl or 'net' in cl) and ('value' in cl or 'val' in cl) and 'improvement' not in cl: total_col = col
    return land_col, impr_col, total_col

def load_roll(roll_path):
    """Load assessor roll regardless of format."""
    ext = os.path.splitext(roll_path)[1].lower()
    if ext in ['.xlsx', '.xls']:
        xl = pd.ExcelFile(roll_path)
        print(f"  Excel sheets: {xl.sheet_names}")
        # Try to auto-detect the right sheet
        for sheet in xl.sheet_names:
            df = xl.parse(sheet)
            apn_col = find_apn_col(df)
            if apn_col:
                print(f"  Using sheet: '{sheet}' | APN col: '{apn_col}'")
                return df
        return xl.parse(xl.sheet_names[0])
    else:
        # Try different encodings/separators
        for enc in ['utf-8', 'latin-1', 'cp1252']:
            try:
                df = pd.read_csv(roll_path, encoding=enc, low_memory=False)
                return df
            except Exception:
                continue
    raise ValueError(f"Could not load roll file: {roll_path}")

def join_roll(county, roll_path):
    county = county.lower()
    cfg = COUNTY_CONFIG.get(county)
    if not cfg:
        print(f"ERROR: Unknown county '{county}'. Add to COUNTY_CONFIG.")
        sys.exit(1)

    call_sheet_path = os.path.join(BASE, cfg["call_sheet"])
    if not os.path.exists(call_sheet_path):
        print(f"ERROR: Call sheet not found: {call_sheet_path}")
        sys.exit(1)

    print(f"\n=== LOADING CALL SHEET: {call_sheet_path} ===")
    df_auction = pd.read_csv(call_sheet_path, low_memory=False)
    print(f"  Auction parcels: {len(df_auction)}")

    print(f"\n=== LOADING ASSESSOR ROLL: {roll_path} ===")
    df_roll = load_roll(roll_path)
    print(f"  Roll rows: {len(df_roll)}")

    # Find key columns
    apn_col = find_apn_col(df_roll)
    land_col, impr_col, total_col = find_value_cols(df_roll)
    print(f"  APN col:   {apn_col}")
    print(f"  Land col:  {land_col}")
    print(f"  Impr col:  {impr_col}")
    print(f"  Total col: {total_col}")

    if not apn_col:
        print("ERROR: Could not find APN column in roll. Check column names:")
        print(df_roll.columns.tolist())
        sys.exit(1)

    # Normalize APNs for matching
    df_roll['_apn_norm'] = df_roll[apn_col].apply(normalize_apn)

    # Find auction APN col
    auction_apn_col = None
    for col in ['Parcel_Number', 'APN', 'apn', 'parcel_number']:
        if col in df_auction.columns:
            auction_apn_col = col
            break
    if not auction_apn_col:
        print(f"ERROR: No APN column found in call sheet. Cols: {df_auction.columns.tolist()}")
        sys.exit(1)

    df_auction['_apn_norm'] = df_auction[auction_apn_col].apply(normalize_apn)

    # Build lookup dict from roll
    roll_lookup = {}
    for _, row in df_roll.iterrows():
        key = row['_apn_norm']
        roll_lookup[key] = {
            'real_land_value':  float(str(row.get(land_col,0) or 0).replace(',','').replace('$','')) if land_col else 0,
            'real_impr_value':  float(str(row.get(impr_col,0) or 0).replace(',','').replace('$','')) if impr_col else 0,
            'real_total_value': float(str(row.get(total_col,0) or 0).replace(',','').replace('$','')) if total_col else 0,
        }

    # Join
    matched = 0
    df_auction['real_land_value']   = 0.0
    df_auction['real_impr_value']   = 0.0
    df_auction['real_total_value']  = 0.0
    df_auction['assessor_verified'] = 'NO'

    for idx, row in df_auction.iterrows():
        key = row['_apn_norm']
        if key in roll_lookup:
            vals = roll_lookup[key]
            df_auction.at[idx, 'real_land_value']   = vals['real_land_value']
            df_auction.at[idx, 'real_impr_value']   = vals['real_impr_value']
            df_auction.at[idx, 'real_total_value']  = vals['real_total_value']
            df_auction.at[idx, 'assessor_verified'] = 'YES'
            matched += 1

    print(f"\n=== JOIN RESULTS ===")
    print(f"  Auction parcels:    {len(df_auction)}")
    print(f"  Matched from roll:  {matched}")
    print(f"  Unmatched:          {len(df_auction) - matched}")

    # Recalculate bid math with real values
    df_auction['net_assessed_value'] = df_auction.apply(
        lambda r: r['real_total_value'] if r['assessor_verified'] == 'YES' and r['real_total_value'] > 0
                  else r.get('net_assessed_value', 0),
        axis=1
    )
    df_auction['nav_source'] = df_auction.apply(
        lambda r: 'CPRA_ASSESSOR_ROLL' if r['assessor_verified'] == 'YES' else r.get('nav_source','ESTIMATED'),
        axis=1
    )
    df_auction['max_bid_70pct']      = (df_auction['net_assessed_value'] * 0.70).round(0)
    df_auction['gross_equity_at_70'] = (df_auction['max_bid_70pct'] - df_auction['min_bid']).round(0)

    # Drop temp columns
    df_auction.drop(columns=['_apn_norm'], inplace=True, errors='ignore')

    # Save updated call sheet
    out_csv = call_sheet_path.replace('.csv', f'_VERIFIED_{datetime.now().strftime("%Y%m%d")}.csv')
    df_auction.to_csv(out_csv, index=False)
    print(f"\nSaved verified call sheet: {out_csv}")

    print(f"\n=== VERIFIED TOP 10 ===")
    top10 = df_auction.sort_values('priority_score', ascending=False).head(10)
    print(top10[[auction_apn_col,'Owner','min_bid','real_total_value','max_bid_70pct','gross_equity_at_70','assessor_verified']].to_string())

    return df_auction

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Join CPRA assessor roll with auction call sheet")
    parser.add_argument("--county", required=True, help="County name (kern, fresno, butte, etc.)")
    parser.add_argument("--roll",   required=True, help="Path to assessor roll file (CSV or Excel)")
    args = parser.parse_args()
    join_roll(args.county, os.path.join(BASE, args.roll))
