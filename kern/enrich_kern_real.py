"""
Kern County Real Parcel Enrichment Engine

SUPERSEDED 2026-08-06 — DO NOT USE FOR REAL ASSESSED VALUES.
Line ~124 falls back to `min_bid * 5.0` (tagged 'ESTIMATED_5X_MIN_BID') for any
parcel where FATCO didn't have a real ASSESSED_TOTAL_VALUE — which was ~88% of
parcels. Verified against the live Kern Assessor site: this formula was off by
~41x on a spot-checked parcel ($260,000 estimated vs $6,336 real).
Use kern_real_pull.py instead — it queries assessorapps.kerncounty.com live
(free, via stealth browser + local OCR CAPTCHA solve) for a real value on every
parcel, no formula, no fallback guess.

- Loads all 940 real auction parcels from FATCO ArcGIS pull
- Enriches each with assessor values from the FATCO full dataset (which has ASSESSED_TOTAL_VALUE etc.)
- Extracts use code, zoning, acreage, IRS lien flags from Property_Description text
- Calculates bid math: 70% max safe bid, bid-to-value ratio
- Priority scores each parcel
- Flags out-of-state owners, IRS liens, vacant land
- Exports final scored call sheet CSV + Excel workbook
"""
import os, re
import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime

BASE = r"C:\Users\chuck\Downloads\county_pipeline\kern"

# ─── LOAD REAL DATA ───────────────────────────────────────────────
print("Loading real Kern County auction data...")

# Load the full FATCO pull (940 auction parcels)
df_raw = pd.read_csv(os.path.join(BASE, "kern_REAL_auction_list_fatco.csv"), low_memory=False)
print(f"Full FATCO dataset: {len(df_raw)} rows")

# Filter to rows with real auction data
df = df_raw[df_raw['Parcel_Number'].notna() & df_raw['Owner'].notna() & df_raw['Minimum_Bid_Owed'].notna()].copy()
df = df.reset_index(drop=True)
print(f"Real auction parcels: {len(df)}")

# ─── PARSE PROPERTY DESCRIPTION ───────────────────────────────────
def parse_description(desc):
    desc = str(desc) if desc else ""
    use_code = re.search(r'Use Code[:\s]+(\d+)', desc)
    zoning = re.search(r'Zoning Classification[:\s]+([^\n\r]+?)(?:A transfer|$)', desc)
    acres = re.search(r'Acres[:\s]+([\d.]+)', desc)
    tax_area = re.search(r'Tax Rate Area[:\s]+([\d\-]+)', desc)
    irs_lien = 'IRS Lien' in desc or 'IRS lien' in desc
    return {
        'use_code': use_code.group(1).strip() if use_code else '',
        'zoning': zoning.group(1).strip()[:60] if zoning else '',
        'acres': float(acres.group(1)) if acres else None,
        'tax_rate_area': tax_area.group(1).strip() if tax_area else '',
        'irs_lien_flag': 'YES' if irs_lien else 'NO',
    }

parsed = df['Property_Description'].apply(parse_description)
df['use_code']       = [p['use_code'] for p in parsed]
df['zoning']         = [p['zoning'] for p in parsed]
df['acres']          = [p['acres'] for p in parsed]
df['tax_rate_area']  = [p['tax_rate_area'] for p in parsed]
df['irs_lien_flag']  = [p['irs_lien_flag'] for p in parsed]

# ─── CLASSIFY USE CODE ────────────────────────────────────────────
def classify_use(use_code):
    code = str(use_code)
    if code.startswith('0'):    return 'RESIDENTIAL'
    elif code.startswith('1'):  return 'COMMERCIAL'
    elif code.startswith('2'):  return 'INDUSTRIAL'
    elif code.startswith('3'):  return 'AGRICULTURE'
    elif code.startswith('4'):  return 'VACANT LAND'
    elif code.startswith('5'):  return 'INSTITUTIONAL'
    else:                       return 'OTHER'

df['property_type'] = df['use_code'].apply(classify_use)

# ─── OWNER & MAILING ──────────────────────────────────────────────
OWNER_COL  = 'Owner'
SITUS_COL  = 'Parcel_Location'
APN_COL    = 'Parcel_Number'
BID_COL    = 'Minimum_Bid_Owed'

# Try to get mailing from FATCO full dataset fields
mail_cols = ['MAIL_STREET_ADDRESS','MAIL_CITY','MAIL_STATE','MAIL_ZIP_CODE']
available_mail = [c for c in mail_cols if c in df.columns]

def build_mailing(row):
    parts = [str(row.get(c,'') or '').strip() for c in available_mail if row.get(c)]
    return ', '.join(p for p in parts if p) or str(row.get(SITUS_COL,'') or '')

if available_mail:
    df['mailing_address'] = df.apply(build_mailing, axis=1)
else:
    df['mailing_address'] = df[SITUS_COL].fillna('')

# Detect out-of-state from mailing
def get_owner_state(row):
    mail = str(row.get('mailing_address','') or '')
    # look for 2-letter state abbrev before ZIP
    m = re.search(r',\s*([A-Z]{2})\s+\d{5}', mail)
    if m:
        return m.group(1)
    # fallback to FATCO mail state field
    return str(row.get('MAIL_STATE','CA') or 'CA').strip()

if 'MAIL_STATE' in df.columns:
    df['owner_state'] = df.apply(get_owner_state, axis=1)
else:
    df['owner_state'] = 'CA'

df['out_of_state'] = df['owner_state'].apply(lambda s: 'YES' if str(s).strip() not in ('CA','') else 'NO')

# ─── ASSESSOR VALUES ──────────────────────────────────────────────
# FATCO has ASSESSED_TOTAL_VALUE in the full pull — use where available
def safe_float(val, default=0.0):
    try:
        return float(val) if pd.notna(val) and val != '' else default
    except:
        return default

df['assessed_total']    = df.get('ASSESSED_TOTAL_VALUE', pd.Series([None]*len(df))).apply(lambda v: safe_float(v))
df['assessed_land']     = df.get('ASSESSED_LAND_VALUE', pd.Series([None]*len(df))).apply(lambda v: safe_float(v))
df['assessed_impr']     = df.get('ASSESSED_IMPROVEMENT_VALUE', pd.Series([None]*len(df))).apply(lambda v: safe_float(v))

# Where assessor values are zero, estimate from min bid (conservative: min bid = ~15-25% of value)
# Use 5x multiplier as floor estimate only when no assessor data
def estimate_nav(row):
    total = row['assessed_total']
    if total > 0:
        return total
    min_bid = safe_float(row.get(BID_COL, 0))
    # Conservative: assume min bid is ~20% of value
    return round(min_bid * 5.0, 0)

df['net_assessed_value'] = df.apply(estimate_nav, axis=1)
df['nav_source'] = df.apply(
    lambda r: 'FATCO_ASSESSOR' if r['assessed_total'] > 0 else 'ESTIMATED_5X_MIN_BID',
    axis=1
)

# ─── BID MATH ─────────────────────────────────────────────────────
df['min_bid']            = df[BID_COL].apply(safe_float)
df['max_bid_70pct']      = (df['net_assessed_value'] * 0.70).round(0)
df['bid_to_value_pct']   = (df['min_bid'] / df['net_assessed_value'].replace(0, 1) * 100).round(1)
df['gross_equity_at_70'] = (df['max_bid_70pct'] - df['min_bid']).round(0)

# ─── PRIORITY SCORE ───────────────────────────────────────────────
def score_parcel(row):
    s = 50.0
    # High equity cushion
    if row['gross_equity_at_70'] > 50000:  s += 20
    elif row['gross_equity_at_70'] > 20000: s += 12
    elif row['gross_equity_at_70'] > 5000:  s += 6
    # Low bid-to-value (cheap entry)
    btv = row['bid_to_value_pct']
    if btv < 15:   s += 15
    elif btv < 25: s += 10
    elif btv < 40: s += 5
    # Residential = higher demand
    if row['property_type'] == 'RESIDENTIAL': s += 10
    elif row['property_type'] == 'COMMERCIAL': s += 5
    # Out of state absentee owner
    if row['out_of_state'] == 'YES': s += 8
    # IRS lien (risk = lower score)
    if row['irs_lien_flag'] == 'YES': s -= 15
    # High min bid (bigger deal)
    if row['min_bid'] > 50000: s += 5
    return min(round(s, 1), 99.9)

df['priority_score'] = df.apply(score_parcel, axis=1)

# ─── FINAL CLEAN COLUMNS ──────────────────────────────────────────
OUTPUT_COLS = [
    'Parcel_Number', OWNER_COL, SITUS_COL, 'mailing_address',
    'owner_state', 'out_of_state',
    'min_bid', 'net_assessed_value', 'nav_source',
    'max_bid_70pct', 'bid_to_value_pct', 'gross_equity_at_70',
    'priority_score',
    'property_type', 'use_code', 'zoning', 'acres',
    'tax_rate_area', 'irs_lien_flag',
    'FLOOD_ZONE_CODE', 'INSIDE_SFHA', 'Tax_Year'
]
OUTPUT_COLS = [c for c in OUTPUT_COLS if c in df.columns or c in [OWNER_COL, SITUS_COL]]

df_out = df[OUTPUT_COLS].copy()
df_out = df_out.sort_values('priority_score', ascending=False).reset_index(drop=True)

# ─── SAVE CSV ─────────────────────────────────────────────────────
csv_path = os.path.join(BASE, "kern_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
df_out.to_csv(csv_path, index=False)
print(f"\nSaved scored call sheet: {csv_path} ({len(df_out)} parcels)")

# ─── BUILD EXCEL WORKBOOK ─────────────────────────────────────────
print("Building Excel workbook...")

wb = openpyxl.Workbook()

NAVY   = "1E3A5F"
ORANGE = "D28228"
WHITE  = "FFFFFF"
GREEN  = "1A7A4A"
RED    = "C0392B"
YELLOW = "F39C12"
LGRAY  = "F2F4F7"

def hdr_fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def hdr_font(bold=True, color=WHITE, size=10):
    return Font(bold=bold, color=color, size=size)

def make_border():
    s = Side(border_style="thin", color="CCCCCC")
    return Border(left=s, right=s, top=s, bottom=s)

def write_sheet(ws, df_tab, title, subtitle):
    ws.sheet_view.showGridLines = False

    # Title row
    ws.merge_cells(f"A1:{get_column_letter(len(df_tab.columns))}1")
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, color=WHITE, size=14)
    ws["A1"].fill = hdr_fill(NAVY)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    # Subtitle
    ws.merge_cells(f"A2:{get_column_letter(len(df_tab.columns))}2")
    ws["A2"] = subtitle
    ws["A2"].font = Font(bold=False, color="AAAAAA", size=9)
    ws["A2"].fill = hdr_fill("162D4A")
    ws["A2"].alignment = Alignment(horizontal="center")
    ws.row_dimensions[2].height = 16

    # Header row
    for col_idx, col in enumerate(df_tab.columns, 1):
        cell = ws.cell(row=3, column=col_idx, value=col.replace("_"," ").title())
        cell.fill = hdr_fill(ORANGE)
        cell.font = hdr_font()
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = make_border()
    ws.row_dimensions[3].height = 36

    # Data rows
    for row_idx, (_, row) in enumerate(df_tab.iterrows(), 4):
        fill = PatternFill("solid", fgColor=LGRAY) if row_idx % 2 == 0 else PatternFill("solid", fgColor=WHITE)
        for col_idx, col in enumerate(df_tab.columns, 1):
            val = row[col]
            if pd.isna(val): val = ""
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = fill
            cell.border = make_border()
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)
            cell.font = Font(size=9)

            # Color priority score
            if col == 'priority_score':
                try:
                    pv = float(val)
                    if pv >= 80:   cell.fill = PatternFill("solid", fgColor="1A7A4A"); cell.font = Font(bold=True, color=WHITE, size=9)
                    elif pv >= 65: cell.fill = PatternFill("solid", fgColor=ORANGE); cell.font = Font(bold=True, color=WHITE, size=9)
                    else:          cell.fill = PatternFill("solid", fgColor="888888"); cell.font = Font(color=WHITE, size=9)
                except: pass

            # Format currency
            if col in ('min_bid','net_assessed_value','max_bid_70pct','gross_equity_at_70'):
                try:
                    cell.number_format = '$#,##0'
                    cell.value = float(val) if val != "" else 0
                except: pass

            if col == 'bid_to_value_pct':
                try:
                    cell.value = f"{float(val):.1f}%"
                except: pass

    # Column widths
    col_widths = {
        'Parcel Number': 18, 'Owner': 28, 'Parcel Location': 24,
        'Mailing Address': 28, 'Owner State': 10, 'Out Of State': 10,
        'Min Bid': 14, 'Net Assessed Value': 18, 'Nav Source': 18,
        'Max Bid 70Pct': 16, 'Bid To Value Pct': 14, 'Gross Equity At 70': 18,
        'Priority Score': 14, 'Property Type': 16, 'Use Code': 10,
        'Zoning': 22, 'Acres': 10, 'Tax Rate Area': 14,
        'Irs Lien Flag': 12, 'Flood Zone Code': 14, 'Inside Sfha': 12, 'Tax Year': 10
    }
    for col_idx, col in enumerate(df_tab.columns, 1):
        key = col.replace("_"," ").title()
        ws.column_dimensions[get_column_letter(col_idx)].width = col_widths.get(key, 14)

    ws.freeze_panes = "A4"

# Tab 1: All 940 parcels
ws1 = wb.active
ws1.title = "All Auction Parcels"
write_sheet(ws1, df_out,
    f"KERN COUNTY — ALL {len(df_out)} AUCTION PARCELS — Sept 14-16, 2026",
    f"Source: First American Title (FATCO) ArcGIS FeatureServer  |  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  Logic Flow Systems")

# Tab 2: Top targets (score >= 75)
df_top = df_out[df_out['priority_score'] >= 75].head(50).reset_index(drop=True)
ws2 = wb.create_sheet("Top Targets (Score 75+)")
write_sheet(ws2, df_top,
    f"KERN COUNTY — TOP {len(df_top)} HIGH-PRIORITY TARGETS",
    "Priority Score >= 75  |  Sorted by Score Descending  |  Logic Flow Systems")

# Tab 3: Residential only
df_res = df_out[df_out['property_type'] == 'RESIDENTIAL'].reset_index(drop=True)
ws3 = wb.create_sheet("Residential Parcels")
write_sheet(ws3, df_res,
    f"KERN COUNTY — RESIDENTIAL PARCELS ({len(df_res)})",
    "Use Code 0xxx  |  Sorted by Priority Score  |  Logic Flow Systems")

# Tab 4: High equity (equity > $20k)
df_eq = df_out[df_out['gross_equity_at_70'] > 20000].reset_index(drop=True)
ws4 = wb.create_sheet("High Equity Plays")
write_sheet(ws4, df_eq,
    f"KERN COUNTY — HIGH EQUITY PLAYS ({len(df_eq)}) — Equity > $20K at 70% NAV",
    "Gross Equity = (70% Net Assessed Value) - Min Bid  |  Logic Flow Systems")

# Save
xlsx_path = os.path.join(BASE, "Kern_Auction_Intel_Workbook_REAL.xlsx")
wb.save(xlsx_path)
print(f"Saved Excel workbook: {xlsx_path}")

# ─── SUMMARY ──────────────────────────────────────────────────────
print("\n" + "="*60)
print("KERN COUNTY ENRICHMENT COMPLETE")
print("="*60)
print(f"Total real parcels:         {len(df_out)}")
print(f"Top priority (score 75+):   {len(df_top)}")
print(f"Residential parcels:        {len(df_res)}")
print(f"High equity plays (>$20K):  {len(df_eq)}")
print(f"IRS liens flagged:          {(df_out['irs_lien_flag']=='YES').sum()}")
print(f"Out-of-state owners:        {(df_out['out_of_state']=='YES').sum()}")
print(f"Min bid total exposure:     ${df_out['min_bid'].sum():,.0f}")
print(f"Est. total equity at 70%:   ${df_out['gross_equity_at_70'].sum():,.0f}")
print(f"\nTop 10 parcels by priority score:")
print(df_out[['Parcel_Number','Owner','Parcel_Location','min_bid','net_assessed_value','max_bid_70pct','gross_equity_at_70','priority_score']].head(10).to_string())
