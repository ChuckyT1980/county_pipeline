"""
Universal Multi-County Data Gathering & Intelligence Engine
Ingests, verifies, scores, and packages tax sale parcel data for ANY California county.

Usage:
    python multi_county_engine.py --county kern
    python multi_county_engine.py --county fresno
    python multi_county_engine.py --county riverside
    python multi_county_engine.py --county shasta
    python multi_county_engine.py --county tehama
    python multi_county_engine.py --county butte
"""
import os
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from config import COUNTY_CONFIG

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import owner_resolve
import null_name_dork_resolver

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PIPELINE_DIR)

def normalize_apn(apn_str):
    if not apn_str or pd.isna(apn_str):
        return ""
    s = re.sub(r"[^0-9]", "", str(apn_str))
    if len(s) == 12:
        return f"{s[:3]}-{s[3:6]}-{s[6:9]}-{s[9:12]}"
    elif len(s) == 10:
        return f"{s[:3]}-{s[3:6]}-{s[6:9]}-{s[9]}"
    elif len(s) == 9:
        return f"{s[:3]}-{s[3:6]}-{s[6:]}"
    return str(apn_str).strip()

def calculate_bid_metrics(min_bid, land_val, imp_val, net_assessed):
    try:
        mb = float(min_bid or 0)
        nav = float(net_assessed or 0)
        if nav <= 0:
            nav = float(land_val or 0) + float(imp_val or 0)
            
        max_safe_bid = round(nav * 0.70, 2) if nav > 0 else 0.0
        bid_to_val_pct = round((mb / nav) * 100.0, 1) if nav > 0 and mb > 0 else 0.0
        return mb, nav, max_safe_bid, bid_to_val_pct
    except Exception:
        return 0.0, 0.0, 0.0, 0.0

def calculate_priority_score(balance, imp_val, land_val, is_absentee, distress_count=0):
    score = 50.0
    bal = float(balance or 0)
    imp = float(imp_val or 0)
    land = float(land_val or 0)
    
    # Balance factor
    if bal >= 50000:
        score += 20
    elif bal >= 20000:
        score += 12
    elif bal >= 5000:
        score += 5
        
    # Real house / improvement factor
    if imp > 0:
        ratio = imp / land if land > 0 else 1.0
        if ratio >= 1.0:
            score += 15
        elif ratio >= 0.5:
            score += 8
            
    # Absentee owner factor
    if is_absentee:
        score += 10
        
    # Distress signals
    score += min(int(distress_count) * 2, 10)
    
    return min(round(score, 1), 99.9)

def generate_county_intel_pack(county_slug, df_parcels):
    county = county_slug.lower().strip()
    county_dir = os.path.join(BASE_DIR, county)
    os.makedirs(county_dir, exist_ok=True)
    
    print(f"\n============================================================")
    print(f"  PROCESSING MULTI-COUNTY INTELLIGENCE: {county.upper()}")
    print(f"  Total Parcels Ingested: {len(df_parcels)}")
    print(f"============================================================\n")

    processed = []
    null_owner_rows = []
    
    for idx, row in df_parcels.iterrows():
        apn = normalize_apn(row.get("apn"))
        owner = str(row.get("owner_name") or row.get("verified_current_owner_name") or "OWNER OF RECORD").strip()
        
        if owner in ("OWNER OF RECORD", "UNKNOWN", "COUNTY_REDACTED_NAME", "None", "", "nan"):
            res = owner_resolve.resolve_owner(apn, county, emit_dorks=True)
            if res.get("owner_name"):
                owner = res.get("owner_name")
            else:
                null_owner_rows.append({"apn": apn})
                
        situs = str(row.get("situs_address") or row.get("property_address") or "PARCEL LOCATION").strip()
        mailing = str(row.get("mailing_address") or "MAILING ADDRESS").strip()
        
        balance = float(row.get("v_total_balance") or row.get("total_tax_billed") or row.get("balance") or 5000)
        min_bid = float(row.get("min_bid") or row.get("minimum_bid") or (balance * 0.75))
        land_val = float(row.get("land_value") or 25000)
        imp_val = float(row.get("improvements_value") or 65000)
        net_assessed = float(row.get("net_assessed_value") or row.get("net_taxable_value") or (land_val + imp_val))
        
        owner_state = str(row.get("owner_state") or "CA").strip()
        is_absentee = (owner_state.upper() != "CA") or ("Y" in str(row.get("out_of_state", "")).upper())
        
        status = str(row.get("redemption_status") or row.get("status") or "ACTIVE").strip().upper()
        if "REDEEM" in status:
            status = "REDEEMED"
            score = 0.0
        else:
            status = "ACTIVE"
            score = calculate_priority_score(balance, imp_val, land_val, is_absentee, row.get("distress_signal_score", 0))

        mb, nav, max_safe, btv = calculate_bid_metrics(min_bid, land_val, imp_val, net_assessed)

        processed.append({
            "apn": apn,
            "verified_current_owner_name": owner,
            "situs_address": situs,
            "mailing_address": mailing,
            "owner_state": owner_state,
            "out_of_state": "Y" if is_absentee else "N",
            "v_total_balance": balance,
            "min_bid": mb,
            "land_value": land_val,
            "improvements_value": imp_val,
            "net_assessed_value": nav,
            "max_bid_threshold": max_safe,
            "bid_to_value_pct": f"{btv:.1f}%" if btv > 0 else "-",
            "priority_score": score,
            "redemption_status": status,
            "fire_hazard_zone": str(row.get("fire_hazard_zone") or "UNZONED"),
            "flood_zone": str(row.get("flood_zone") or "X"),
            "verification_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    df_out = pd.DataFrame(processed)

    # 1. Save Call Sheet CSV
    call_sheet_csv = os.path.join(county_dir, f"{county}_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
    df_out.to_csv(call_sheet_csv, index=False)
    print(f"  [1/3] Call Sheet CSV: {call_sheet_csv} ({len(df_out)} rows)")

    # 2. Save Targets CSV
    targets_csv = os.path.join(county_dir, f"{county}_auction_targets_with_values.csv")
    df_out[["apn", "verified_current_owner_name", "min_bid", "net_assessed_value", "max_bid_threshold", "bid_to_value_pct", "priority_score", "redemption_status"]].to_csv(targets_csv, index=False)
    print(f"  [2/3] Auction Targets CSV: {targets_csv}")

    # 3. Save Formatted Excel Intelligence Workbook
    excel_path = os.path.join(county_dir, f"{county.title()}_Auction_Intel_Workbook.xlsx")
    wb = openpyxl.Workbook()
    
    ws1 = wb.active
    ws1.title = "Auction Leads (Pre-Scored)"
    ws2 = wb.create_sheet(title="Top 20 Targets (Safe Bids)")
    ws3 = wb.create_sheet(title="Redemption Verification")
    
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    fill_navy = PatternFill(start_color="1F3A5F", end_color="1F3A5F", fill_type="solid")
    border_thin = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )

    # Add All Leads
    ws1.append(list(df_out.columns))
    for cell in ws1[1]:
        cell.font = font_header
        cell.fill = fill_navy
        cell.alignment = Alignment(horizontal="center")
        
    for r in df_out.values:
        ws1.append(list(r))

    # Add Top Targets
    df_top = df_out[df_out["redemption_status"] == "ACTIVE"].sort_values(by="priority_score", ascending=False).head(20)
    ws2.append(list(df_top.columns))
    for cell in ws2[1]:
        cell.font = font_header
        cell.fill = fill_navy
        cell.alignment = Alignment(horizontal="center")
    for r in df_top.values:
        ws2.append(list(r))

    # Auto-fit columns
    for ws in [ws1, ws2, ws3]:
        ws.views.sheetView[0].showGridLines = True
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    if null_owner_rows:
        out_path = Path(county_dir) / "null_name_dorks.html"
        null_name_dork_resolver.generate_dorks_html(null_owner_rows, county, out_path)
        print(f"  [4/4] Dork URLs generated for {len(null_owner_rows)} missing owners: {out_path}")

    print(f"\nSuccessfully generated multi-county intelligence package for {county.upper()}!\n")
    return call_sheet_csv, targets_csv, excel_path

def main():
    parser = argparse.ArgumentParser(description="Multi-County Data Gathering & Intelligence Engine")
    parser.add_argument("--county", required=True, help="County slug (e.g. kern, fresno, riverside, shasta, tehama, butte, los_angeles)")
    parser.add_argument("--input-csv", default=None, help="Optional input parcel CSV")
    args = parser.parse_args()

    county_slug = args.county.lower().strip()
    
    # Determine input data source
    if args.input_csv and os.path.exists(args.input_csv):
        df_in = pd.read_csv(args.input_csv)
    else:
        # Check existing pipeline discovery files
        county_dir = os.path.join(BASE_DIR, county_slug)
        existing_callsheet = os.path.join(county_dir, f"{county_slug}_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
        existing_master = os.path.join(county_dir, f"{county_slug}_AUTHORITATIVE_master_index.csv")
        pipeline_all = os.path.join(PIPELINE_DIR, f"{county_slug}_all_auction_parcels.csv")
        
        if os.path.exists(existing_callsheet):
            df_in = pd.read_csv(existing_callsheet)
        elif os.path.exists(existing_master):
            df_in = pd.read_csv(existing_master)
        elif os.path.exists(pipeline_all):
            df_in = pd.read_csv(pipeline_all)
        else:
            # Seed dataset for demo / test county execution
            print(f"No existing CSV found for {county_slug.upper()} — building seed dataset from config...")
            df_in = pd.DataFrame([
                {"apn": "010-120-001-000", "owner_name": "CALIFORNIA INVESTMENTS LLC", "situs_address": "100 MAIN ST", "mailing_address": "PO BOX 100", "v_total_balance": 18500.0, "min_bid": 12000.0, "land_value": 35000.0, "improvements_value": 85000.0, "owner_state": "CA"},
                {"apn": "010-120-002-000", "owner_name": "SMITH ARLENE TRUSTEE", "situs_address": "240 OAK AVE", "mailing_address": "450 1ST ST, RENO NV", "v_total_balance": 34200.0, "min_bid": 18500.0, "land_value": 40000.0, "improvements_value": 11000.0, "owner_state": "NV"},
                {"apn": "010-120-003-000", "owner_name": "JOHNSON ROBERT E", "situs_address": "580 PINE RD", "mailing_address": "580 PINE RD", "v_total_balance": 9800.0, "min_bid": 6500.0, "land_value": 20000.0, "improvements_value": 55000.0, "owner_state": "CA"},
                {"apn": "010-120-004-000", "owner_name": "WESTERN HOLDINGS INC", "situs_address": "890 ELM ST", "mailing_address": "1200 BROADWAY, NEW YORK NY", "v_total_balance": 65000.0, "min_bid": 42000.0, "land_value": 60000.0, "improvements_value": 140000.0, "owner_state": "NY"},
                {"apn": "010-120-005-000", "owner_name": "DAVIS MICHAEL & SARAH", "situs_address": "310 CEDAR LN", "mailing_address": "310 CEDAR LN", "v_total_balance": 14300.0, "min_bid": 9800.0, "land_value": 30000.0, "improvements_value": 75000.0, "owner_state": "CA"}
            ])

    generate_county_intel_pack(county_slug, df_in)

if __name__ == "__main__":
    main()
