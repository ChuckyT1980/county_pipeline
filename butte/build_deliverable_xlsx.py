"""
Buyer-facing XLSX build for the Butte auction call sheet.

Takes the raw internal CSV (40+ columns of pipeline noise) and produces a
clean Excel workbook the buyer will actually open:

  Sheet 1 "Leads"          — reordered + renamed columns, formatting, frozen header,
                             priority-based color rows, currency/date formatting
  Sheet 2 "Verification"   — per-parcel confidence + provenance for buyers who want the audit trail
  Sheet 3 "Doc References" — recorder doc numbers + types + dates for lookups
  Sheet 4 "How to Use"     — column dictionary + workflow guide
"""
import argparse
import os
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


# Column ordering + human-readable names for the primary Leads sheet
LEADS_COLUMNS = [
    # ("csv_column", "Display Name", width, format)
    ("priority_score",              "Priority",              10, "0.0"),
    ("apn",                         "APN",                   17, None),
    ("verified_current_owner_name", "Owner",                 32, None),
    ("ownership_class",             "Owner Type",            13, None),
    ("v_total_balance",             "Defaulted Balance",     18, None),
    ("situs_address",               "Property Address",      34, None),
    ("mailing_address",             "Mailing Address",       44, None),
    ("owner_state",                 "State",                  7, None),
    ("out_of_state",                "Absentee",              10, None),
    ("fire_hazard_zone",            "Fire Hazard",           14, None),
    ("flood_zone",                  "Flood Zone",            11, None),
    ("portfolio_apn_count",         "Portfolio Size",        14, "0"),
    ("portfolio_apn_balance",       "Portfolio $ Total",     18, "$#,##0.00"),
    ("distress_signal_score",       "Distress Score",        14, "0"),
    ("distress_signals",            "Distress Signals",      45, None),
    ("business_partners",           "Known Partners",        45, None),
    ("phone_number",                "Phone",                 14, None),
    ("call_date_1",                 "Call 1 Date",           12, None),
    ("outcome_1",                   "Call 1 Outcome",        16, None),
    ("call_date_2",                 "Call 2 Date",           12, None),
    ("outcome_2",                   "Call 2 Outcome",        16, None),
    ("next_action",                 "Next Action",           22, None),
    ("notes",                       "Notes",                 40, None),
]

VERIFICATION_COLUMNS = [
    ("apn",                         "APN",                   17),
    ("verified_current_owner_name", "Owner",                 32),
    ("verification_score",          "Verification %",        15),
    ("verification_sources",        "Data Sources Used",     40),
    ("verification_flag_count",     "Data Flags",            12),
    ("ownership_confidence",        "Owner Confidence",      17),
    ("ownership_flags",             "Owner Signals",         35),
    ("owner_name_source",           "Owner Source",          24),
    ("owner_name_confidence",       "Owner Conf.",           12),
    ("mailing_address_source",      "Mailing Source",        18),
    ("mailing_address_confidence",  "Mailing Conf.",         14),
    ("situs_address_source",        "Situs Source",          15),
    ("situs_address_confidence",    "Situs Conf.",           12),
]

DOC_REF_COLUMNS = [
    ("apn",                    "APN",                17),
    ("verified_current_owner_name", "Owner",         32),
    ("recorder_doc_count",     "# of Docs",          10),
    ("recorder_doc_numbers",   "Recorder Doc #s",    46),
    ("recorder_doc_types",     "Doc Types",          36),
    ("recorder_doc_dates",     "Recording Dates",    36),
]


# Styling
BRAND_DARK    = "1F3A5F"   # deep navy
BRAND_ACCENT  = "2E86AB"   # accent blue
BRAND_LIGHT   = "E8F1F7"   # pale blue for zebra
BRAND_HIGH    = "FFE8C8"   # highlight for top-priority rows
FONT_NAME     = "Calibri"

_thin = Side(border_style="thin", color="C0C0C0")
BORDER_ALL = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)


def _money_to_float(s):
    if pd.isna(s):
        return None
    try:
        return float(str(s).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def _fmt_money_cell(val):
    """Convert a possibly-money-string value into a numeric so Excel can format it."""
    v = _money_to_float(val)
    return v if v is not None else val


def _clean_str(v):
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none"):
        return ""
    return s


def _write_header(ws, columns, row=1):
    header_font = Font(name=FONT_NAME, size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor=BRAND_DARK)
    for col_idx, spec in enumerate(columns, start=1):
        display_name = spec[1]
        width = spec[2]
        cell = ws.cell(row=row, column=col_idx, value=display_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)
        cell.border = BORDER_ALL
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.row_dimensions[row].height = 22


def _apply_zebra_and_border(ws, columns, start_row=2):
    zebra_fill = PatternFill("solid", fgColor=BRAND_LIGHT)
    for r in range(start_row, ws.max_row + 1):
        for c in range(1, len(columns) + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = BORDER_ALL
            cell.alignment = Alignment(vertical="center", wrap_text=False)
            if r % 2 == 0:
                cell.fill = zebra_fill


def _build_leads_sheet(wb: Workbook, df: pd.DataFrame) -> None:
    ws = wb.create_sheet("Leads", 0)
    _write_header(ws, LEADS_COLUMNS)

    # Sort by priority descending
    df["_ps_num"] = pd.to_numeric(df.get("priority_score"), errors="coerce")
    df = df.sort_values("_ps_num", ascending=False)

    high_fill = PatternFill("solid", fgColor=BRAND_HIGH)

    for r_offset, (_, row) in enumerate(df.iterrows(), start=2):
        priority = row.get("_ps_num") or 0
        for c_idx, spec in enumerate(LEADS_COLUMNS, start=1):
            csv_col, disp, width, fmt = spec
            raw = row.get(csv_col)
            if csv_col in ("v_total_balance", "portfolio_apn_balance"):
                cell_val = _fmt_money_cell(raw)
            elif csv_col in ("priority_score", "distress_signal_score", "portfolio_apn_count"):
                try:
                    cell_val = float(raw) if raw not in (None, "") and not pd.isna(raw) else None
                except (ValueError, TypeError):
                    cell_val = None
            else:
                cell_val = _clean_str(raw)
            cell = ws.cell(row=r_offset, column=c_idx, value=cell_val)
            cell.font = Font(name=FONT_NAME, size=10)
            if fmt:
                cell.number_format = fmt
            if csv_col in ("v_total_balance", "portfolio_apn_balance"):
                cell.number_format = "$#,##0"
            # Highlight top-priority rows
            if priority >= 80:
                cell.fill = high_fill

    _apply_zebra_and_border(ws, LEADS_COLUMNS)
    ws.freeze_panes = "D2"  # freeze first 3 cols (Priority, APN, Owner) + header
    ws.sheet_view.zoomScale = 100


def _build_verification_sheet(wb: Workbook, df: pd.DataFrame) -> None:
    ws = wb.create_sheet("Verification")
    # Convert to (col, name, width, fmt=None) shape for reuse
    cols_spec = [(c, n, w, None) for c, n, w in VERIFICATION_COLUMNS]
    _write_header(ws, cols_spec)
    for r_offset, (_, row) in enumerate(df.iterrows(), start=2):
        for c_idx, (csv_col, _, _) in enumerate(VERIFICATION_COLUMNS, start=1):
            cell = ws.cell(row=r_offset, column=c_idx, value=_clean_str(row.get(csv_col)))
            cell.font = Font(name=FONT_NAME, size=10)
    _apply_zebra_and_border(ws, cols_spec)
    ws.freeze_panes = "C2"


def _build_doc_ref_sheet(wb: Workbook, df: pd.DataFrame) -> None:
    ws = wb.create_sheet("Doc References")
    cols_spec = [(c, n, w, None) for c, n, w in DOC_REF_COLUMNS]
    _write_header(ws, cols_spec)
    for r_offset, (_, row) in enumerate(df.iterrows(), start=2):
        for c_idx, (csv_col, _, _) in enumerate(DOC_REF_COLUMNS, start=1):
            cell = ws.cell(row=r_offset, column=c_idx, value=_clean_str(row.get(csv_col)))
            cell.font = Font(name=FONT_NAME, size=10)
    _apply_zebra_and_border(ws, cols_spec)
    ws.freeze_panes = "C2"


def _build_how_to_use_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("How to Use")
    title_font = Font(name=FONT_NAME, size=16, bold=True, color=BRAND_DARK)
    h2_font    = Font(name=FONT_NAME, size=12, bold=True, color=BRAND_DARK)
    body_font  = Font(name=FONT_NAME, size=11)

    ws["A1"] = "How to Work This List"
    ws["A1"].font = title_font
    ws.row_dimensions[1].height = 26

    sections = [
        ("Prioritization",
         "Rows are sorted by Priority Score (0-100). Score is a log-scaled function of defaulted balance: "
         "linear 50-80 for balances under $50k, log 80-100 for $50k to $2.5M. Highlighted rows (score >= 80) "
         "are your highest-dollar targets."),

        ("Portfolio owners",
         "Portfolio Size > 1 means the owner holds multiple parcels on this auction. Call them once about "
         "all their parcels — one conversation, multiple deals. The 'Portfolio $ Total' column shows their "
         "combined defaulted balance across the auction."),

        ("Distress signals",
         "Distress Score (0-100) rolls up historical NODs, IRS liens, judgment liens, and tax defaults per owner. "
         "Signals column lists positive indicators (unresolved_liens, prior_nods, tax_defaults, etc.). Higher score = "
         "owner has been in trouble for longer, more likely to sell."),

        ("Fire hazard",
         "Fire Hazard column reflects CalFire Fire Hazard Severity Zone. 'Very High' = state-designated hazard, "
         "may be uninsurable, materially affects price. Use to filter properties you won't touch or to price aggressively."),

        ("Business partners",
         "Known Partners column lists co-grantees, lenders, and related entities from the recorder graph. "
         "Useful to identify LLC officers, spouses, trustees, and lender relationships without extra research."),

        ("Absentee owners",
         "Absentee=Y means mailing state != CA (out-of-state owner). Traditional wholesaler goldmine: "
         "less attachment, more likely to sell at discount. This list has 19 out-of-state owners."),

        ("Recorder doc numbers",
         "See the 'Doc References' sheet. Every parcel with a recorder doc has the document number listed — "
         "look up at recorder.buttecounty.net to verify title, pull the deed, or research further."),

        ("Verification tab",
         "The 'Verification' sheet shows the source and confidence for every data point. Any lead you want to "
         "double-check, you can see exactly where the owner name / mailing / situs came from."),

        ("Call log columns",
         "Blank columns (Call 1 Date, Outcome 1, Next Action, Notes) are for your workflow. Fill in as you work "
         "the list. Sort/filter by these to track your pipeline."),
    ]
    row = 3
    for title, body in sections:
        ws.cell(row=row, column=1, value=title).font = h2_font
        row += 1
        cell = ws.cell(row=row, column=1, value=body)
        cell.font = body_font
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[row].height = 50
        row += 2

    ws.column_dimensions["A"].width = 120
    ws.sheet_view.zoomScale = 110


def build(csv_path: str, xlsx_path: str) -> str:
    df = pd.read_csv(csv_path, dtype=str)

    wb = Workbook()
    default_ws = wb.active
    wb.remove(default_ws)  # we build our sheets from scratch

    _build_leads_sheet(wb, df)
    _build_verification_sheet(wb, df)
    _build_doc_ref_sheet(wb, df)
    _build_how_to_use_sheet(wb)

    # Set active sheet to Leads
    wb.active = wb.sheetnames.index("Leads")

    wb.save(xlsx_path)
    return xlsx_path


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"))
    p.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "butte_auction_call_sheet.xlsx"))
    args = p.parse_args()
    out = build(args.csv, args.out)
    size = os.path.getsize(out)
    print(f"Wrote {out} ({size:,} bytes)")
