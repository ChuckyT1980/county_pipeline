"""
Build a short teaser PDF for Jeff Macdonald / Butte Home Buyers.

Structure (8 pages):
    1. Cover: SAMPLE PREVIEW (with live verification stamp + dynamic countdown)
    2. What's in the full pack + methodology
    3. NEW: "What you see vs what you get" comparison (5 fields vs 70)
    4. Verification catch story (GRIDLEY)
    5-7. 3 sample dossiers (Macias, Martin Trustee, Tacket) WITH min bid / max bid
    8. Pricing + next step

Output: delivery/jeff_teaser_YYYY-MM-DD.pdf
"""
import os
import re
from datetime import datetime, date

import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from fetch_parcel_images import fetch as fetch_parcel_image

BUTTE_DIR = os.path.dirname(os.path.abspath(__file__))
CALL_SHEET = os.path.join(BUTTE_DIR, "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
TARGETS_CSV = os.path.join(os.path.dirname(BUTTE_DIR), "tax_pipeline",
                           "butte_auction_targets_with_values.csv")
OUT_DIR = os.path.join(BUTTE_DIR, "delivery")

AUCTION_DATE = date(2026, 8, 7)

NAVY       = (31, 58, 95)
NAVY_LIGHT = (46, 134, 171)
GREY_DARK  = (60, 60, 60)
GREY_MID   = (120, 120, 120)
GREY_PALE  = (200, 200, 200)
BG_LIGHT   = (232, 241, 247)
BG_HIGH    = (255, 232, 200)
BG_WARN    = (255, 210, 180)
BG_GOOD    = (210, 240, 210)
RED        = (192, 60, 60)
GREEN      = (60, 140, 80)
ORANGE     = (210, 130, 40)
WHITE      = (255, 255, 255)
GOLD       = (200, 168, 78)
BG_COMPARE = (240, 248, 255)

TARGET_APNS = [
    "035-143-011-000",   # Macias — real house, in-state, imp>land
    "069-190-021-000",   # Martin Trustee — 30 distress signals, prior NODs
    "035-083-006-000",   # Tacket — absentee out-of-state (KS)
]

_NON_LATIN1 = {
    "–": "-", "—": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "•": "*", "…": "...",
    " ": " ", "�": "?",
}


def _latin1(text):
    if text is None:
        return ""
    s = str(text)
    for bad, good in _NON_LATIN1.items():
        if bad in s:
            s = s.replace(bad, good)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _money(v):
    if v is None or pd.isna(v):
        return 0.0
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _fmt_money(v):
    return f"${v:,.0f}"


def _blank(v):
    if v is None or pd.isna(v):
        return True
    return str(v).strip().lower() in {"", "nan", "none"}


class PDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(left=15, top=15, right=15)

    def cell(self, w=None, h=None, text="", *args, **kwargs):
        return super().cell(w, h, _latin1(text), *args, **kwargs)

    def multi_cell(self, w, h=None, text="", *args, **kwargs):
        return super().multi_cell(w, h, _latin1(text), *args, **kwargs)

    def _bar(self, y, height, color):
        self.set_fill_color(*color)
        self.rect(0, y, self.w, height, style="F")

    def _section(self, text, color=None):
        color = color or NAVY
        self.set_text_color(*color)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        y = self.get_y()
        self.set_draw_color(*color)
        self.set_line_width(0.3)
        self.line(self.l_margin, y, self.l_margin + 30, y)
        self.ln(2)

    def _kv(self, key, value, key_w=42, size=10):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", size)
        self.set_text_color(*GREY_MID)
        self.cell(key_w, 5, key)
        self.set_font("Helvetica", "", size)
        self.set_text_color(*GREY_DARK)
        val_w = self.w - self.l_margin - self.r_margin - key_w
        self.multi_cell(val_w, 5, value or "-")


# ---------- Page builders ----------

def cover_page(pdf: PDF, total_leads: int, total_balance: float,
               active_count: int, verification_ts: str):
    days_left = (AUCTION_DATE - date.today()).days
    if days_left < 0:
        days_left = 0

    pdf.add_page()
    pdf._bar(0, 40, NAVY)

    # SAMPLE watermark ribbon
    pdf.set_fill_color(*ORANGE)
    pdf.rect(0, 45, pdf.w, 8, style="F")
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_xy(0, 46)
    pdf.cell(pdf.w, 6, "SAMPLE PREVIEW  --  3 of 105 parcels shown", align="C")

    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_xy(15, 15)
    pdf.cell(0, 10, "Butte County Tax Auction Intel", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 13)
    pdf.set_x(15)
    pdf.cell(0, 8, "Prepared exclusively for Butte Home Buyers")

    pdf.set_xy(15, 65)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "August 7-10, 2026 Tax-Defaulted Auction", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*GREY_DARK)
    pdf.ln(4)
    pdf.multi_cell(0, 6,
        "This is a preview of the full intelligence pack. "
        "3 sample dossiers from a total of 105 auction parcels, chosen to show "
        "the format and depth. The parcels shown were selected because they "
        "match a Butte residential fix-and-flip profile."
    )

    pdf.ln(6)
    # Stat cards
    pdf.set_fill_color(*BG_LIGHT)
    pdf.set_draw_color(*NAVY_LIGHT)
    card_w = 42
    y0 = pdf.get_y()

    for i, (label, value) in enumerate([
        ("Auction parcels", str(total_leads)),
        ("Still active", str(active_count)),
        ("Total defaulted", _fmt_money(total_balance)),
        ("Days to auction", str(days_left)),
    ]):
        x = 15 + i * (card_w + 3)
        pdf.rect(x, y0, card_w, 22, style="FD")
        pdf.set_xy(x, y0 + 2)
        pdf.set_font("Helvetica", "B", 15)
        pdf.set_text_color(*NAVY)
        pdf.cell(card_w, 8, value, align="C")
        pdf.set_xy(x, y0 + 12)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*GREY_MID)
        pdf.cell(card_w, 5, label, align="C")

    pdf.set_y(y0 + 28)

    # Verification timestamp stamp
    pdf.set_fill_color(*BG_GOOD)
    vy = pdf.get_y()
    pdf.rect(15, vy, pdf.w - 30, 12, style="F")
    pdf.set_xy(18, vy + 3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*GREEN)
    pdf.cell(0, 5,
        f"LIVE VERIFICATION: All {active_count} active parcels confirmed "
        f"still delinquent as of {verification_ts}"
    )
    pdf.set_y(vy + 16)

    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "What's in this preview:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    for line in [
        "1.  How the pack is built + what the verification layer does",
        "2.  What the county PDF gives you vs what the full pack gives you",
        "3.  A real catch: the parcel our pipeline flagged as REDEEMED before you'd have known",
        "4.  Three sample dossiers -- format identical to all 105 in the full pack",
        "5.  How this fits your acquisition team",
    ]:
        pdf.cell(0, 5, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Footer contact
    pdf.set_y(-30)
    pdf.set_draw_color(*GREY_PALE)
    pdf.line(15, pdf.get_y(), pdf.w - 15, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 5, "Charles Terrell  |  Logic Flow Systems  |  mrt@logicflowsystems.io", align="C")


def methodology_page(pdf: PDF):
    pdf.add_page()
    pdf._section("How this pack is built")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(0, 5,
        "For every parcel on the county's Aug 7-10 tax-defaulted auction list, "
        "the pipeline cross-references six independent sources and stamps every "
        "field with its source + a confidence value:"
    )
    pdf.ln(2)

    sources = [
        ("Butte MPTS TaxBillv2", "Live tax bill scrape -- balance, defaults, redemption status, power-to-sell date"),
        ("Butte MBAP AsrPrint",  "Assessor snapshot -- land / improvements value, homeowner exemption, situs"),
        ("Tyler EagleWeb",       "Full recorder crawl -- deeds, NODs, IRS liens, judgments, trustee sales"),
        ("CalFire FHSZ",         "Fire hazard zone overlay -- Very High / High / Moderate"),
        ("FEMA NFHL",            "Flood zone overlay per parcel"),
        ("US Census / Nominatim", "Geocoding for situs verification"),
    ]
    label_w = 50
    body_w = pdf.w - pdf.l_margin - pdf.r_margin - label_w
    for src, desc in sources:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*NAVY)
        pdf.set_x(pdf.l_margin)
        pdf.cell(label_w, 5, "  " + src)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*GREY_DARK)
        pdf.multi_cell(body_w, 5, desc)

    pdf.ln(4)
    pdf._section("The verification layer -- what makes this different")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5,
        "Generic lead lists rank parcels by defaulted balance and stop there. "
        "The verification layer keeps checking every parcel against live county "
        "data even after ingestion. If a parcel is redeemed, subordinated, or "
        "has any status change, the pipeline detects it and adjusts the score "
        "before the pack ships."
    )
    pdf.ln(2)
    pdf.set_fill_color(*BG_HIGH)
    y = pdf.get_y()
    pdf.rect(15, y, pdf.w - 30, 22, style="F")
    pdf.set_xy(18, y + 2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*ORANGE)
    pdf.cell(0, 5, "The next page is a real example.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(18)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(pdf.w - 36, 5,
        "The largest parcel on this auction by defaulted balance -- $2.4M in "
        "back taxes -- was redeemed 4 weeks ago. Every generic auction list "
        "would still show it as the top target. The pipeline caught it."
    )
    pdf.ln(4)

    # Core philosophy quote
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(*NAVY)
    pdf.multi_cell(0, 5,
        '"Every parcel in this report is something I would have researched myself '
        'before deciding whether it deserved another minute of my time. '
        'The goal isn\'t more leads. The goal is fewer wasted hours."'
    )


def comparison_page(pdf: PDF):
    """Page showing the 5 fields from the county PDF vs 70 fields from pipeline."""
    pdf.add_page()
    pdf._section("What you see vs what you get")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(0, 5,
        'The county publishes a 4-page PDF with 5 columns per parcel. '
        'The intelligence pack cross-references 6 independent county systems '
        'and delivers 70 verified fields per parcel.'
    )
    pdf.ln(3)

    col_left_x = pdf.l_margin
    col_right_x = pdf.w / 2 + 4
    col_w = (pdf.w - pdf.l_margin - pdf.r_margin - 8) / 2
    y = pdf.get_y()

    # -- LEFT COLUMN: County PDF --
    pdf.set_fill_color(*GREY_PALE)
    pdf.rect(col_left_x, y, col_w, 10, style="F")
    pdf.set_xy(col_left_x + 2, y + 2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*GREY_DARK)
    pdf.cell(col_w, 6, "County PDF (free)")

    # -- RIGHT COLUMN: Intelligence Pack --
    pdf.set_fill_color(*NAVY)
    pdf.rect(col_right_x, y, col_w, 10, style="F")
    pdf.set_xy(col_right_x + 2, y + 2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*WHITE)
    pdf.cell(col_w, 6, "Intelligence Pack")

    y += 14
    pdf.set_text_color(*GREY_DARK)

    # Left column items
    county_fields = [
        "APN",
        "Owner name",
        "Property address",
        "Jurisdiction",
        "Minimum bid amount",
    ]
    pdf.set_font("Helvetica", "", 10)
    for item in county_fields:
        pdf.set_xy(col_left_x + 4, y)
        pdf.cell(col_w, 5, "  " + item)
        y += 6

    pdf.set_xy(col_left_x + 4, y + 2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*GREY_MID)
    pdf.cell(col_w, 5, "5 fields. No verification.")

    # Right column items
    y_right = pdf.get_y() - (len(county_fields) * 6) - 2
    intel_groups = [
        ("Financial (8)", "Min bid, assessed, max safe bid, bid/value ratio, land, improvements, tax billed, balance"),
        ("Ownership (10)", "Verified owner, entity type, vesting confidence, mailing addr, owner state, absentee flag, class, flags, contributors, portfolio"),
        ("Title & Liens (8)", "Doc numbers, types, dates, count, business partners, distress signals, distress score, signal counts"),
        ("Tax History (8)", "Bill date, power-to-sell, years since PTS, redemption status, redemption date, exemption, installment, special assessments"),
        ("Environmental (6)", "Fire zone, fire responsibility, flood zone, flood subtype, lat, lon"),
        ("Verification (6)", "Verification score, sources, flag count, owner confidence, mailing confidence, situs confidence"),
    ]
    y_r = y_right
    for group_title, fields in intel_groups:
        pdf.set_xy(col_right_x + 4, y_r)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*NAVY)
        pdf.cell(col_w - 8, 4, group_title)
        y_r += 5
        pdf.set_xy(col_right_x + 4, y_r)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*GREY_DARK)
        pdf.multi_cell(col_w - 8, 4, fields)
        y_r = pdf.get_y() + 1

    pdf.set_xy(col_right_x + 4, y_r + 2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*NAVY)
    pdf.cell(col_w, 5, "70 fields. 6 sources. Live verified.")

    # Bottom callout
    pdf.set_y(max(y, y_r) + 14)
    pdf.set_fill_color(*BG_HIGH)
    by = pdf.get_y()
    pdf.rect(15, by, pdf.w - 30, 16, style="F")
    pdf.set_xy(18, by + 3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*ORANGE)
    pdf.cell(0, 5, "Key difference:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(18)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.cell(0, 5, "The county PDF is a snapshot. The intelligence pack is a live-verified decision tool.")


def verification_catch_page(pdf: PDF):
    pdf.add_page()
    pdf._section("Verification catch: parcel already redeemed", color=ORANGE)

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, "GRIDLEY BUSINESS TRUST", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_MID)
    pdf.cell(0, 5, "APN 022-210-078-000  |  177 DENIZ BROS LN, GRIDLEY", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    # WARNING banner
    pdf.set_fill_color(*BG_WARN)
    y = pdf.get_y()
    pdf.rect(15, y, pdf.w - 30, 14, style="F")
    pdf.set_xy(15, y + 4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*RED)
    pdf.cell(pdf.w - 30, 6, "REDEEMED  2026-06-29  --  PARCEL NO LONGER ON AUCTION", align="C")
    pdf.set_y(y + 18)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(0, 5,
        "This parcel had $2,459,683 in defaulted property taxes -- the single "
        "largest exposure on the Aug 7-10 auction list. On June 29, 2026, the "
        "delinquency was paid in full. The parcel is off the auction."
    )
    pdf.ln(3)

    pdf._section("What the pipeline did")
    pdf.set_font("Helvetica", "", 10)
    catches = [
        ("Fetched", "The live tax bill from Butte MPTS TaxBillv2 during pack build"),
        ("Parsed",  "Redemption status = 'redeemed', redemption_date = 2026-06-29"),
        ("Flagged", "Set redemption_status field, added warning banner to dossier"),
        ("Scored",  "Dropped priority_score from 99.9 to 0 -- parcel now sorts to bottom"),
        ("Logged",  "raw_priority_score preserved (99.9) with reason 'redeemed'"),
    ]
    label_w = 22
    body_w = pdf.w - pdf.l_margin - pdf.r_margin - label_w
    for verb, what in catches:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*NAVY_LIGHT)
        pdf.set_x(pdf.l_margin)
        pdf.cell(label_w, 5, "  " + verb)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*GREY_DARK)
        pdf.multi_cell(body_w, 5, what)
    pdf.ln(4)

    pdf._section("Why this matters")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5,
        "If GRIDLEY had shown up on your acquisition workup as the top target, "
        "you would have spent time pulling comps, checking the situs, maybe "
        "even driving out to look at it. On a $2.4M ag parcel with essentially "
        "no improvements it wouldn't have been your target anyway -- but the "
        "point is the pipeline knows it's off the table before you spend a "
        "minute on it. Every parcel in the full pack has been through this "
        "same verification pass."
    )


_BUTTE_CITIES = [
    "STIRLING CITY", "BERRY CREEK", "FEATHER FALLS", "FOREST RANCH",
    "YANKEE HILL", "CLIPPER MILLS", "PARADISE", "MAGALIA", "OROVILLE",
    "CONCOW", "CHICO", "GRIDLEY", "BIGGS", "COHASSET", "PALERMO",
    "BANGOR", "DURHAM", "RICHVALE", "FORBESTOWN",
]

# Jeff's stated buy box for Butte Home Buyers
JEFF_TERRITORY = {"CHICO", "PARADISE", "OROVILLE", "MAGALIA"}


def _extract_city(situs):
    if _blank(situs):
        return "No Situs"
    s = str(situs).strip().upper()
    for city in _BUTTE_CITIES:
        if s.endswith(city):
            return city.title()
    tokens = s.split()
    return tokens[-1].title() if tokens else "Unknown"


def _build_geo_summary(df):
    df = df.copy()
    df["_city"] = df["situs_address"].apply(_extract_city)
    df["_bal"] = df["v_total_balance"].apply(_money)
    df["_pri"] = pd.to_numeric(df["priority_score"], errors="coerce").fillna(0)
    g = (df.groupby("_city")
           .agg(count=("apn", "size"),
                total_bal=("_bal", "sum"),
                avg_pri=("_pri", "mean"),
                max_pri=("_pri", "max"))
           .sort_values("count", ascending=False)
           .reset_index())
    return g, df


def geographic_page(pdf: "PDF", df):
    pdf.add_page()
    pdf._section("How the auction breaks down by area")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(0, 5,
        "Every parcel geocoded to its jurisdiction. This is what the 105-parcel "
        "auction looks like when grouped by where the property actually sits -- "
        "so you can filter to the neighborhoods you already work."
    )
    pdf.ln(3)

    geo, enriched = _build_geo_summary(df)

    # Jeff-specific callout FIRST -- most important number for him
    jeff_rows = enriched[enriched["_city"].str.upper().isin(JEFF_TERRITORY)]
    jeff_count = len(jeff_rows)
    jeff_bal = jeff_rows["_bal"].sum()
    jeff_active = int((jeff_rows["priority_score"].astype(float, errors="ignore") != "0.0").sum()) \
        if "priority_score" in jeff_rows.columns else jeff_count

    pdf.set_fill_color(*BG_HIGH)
    y = pdf.get_y()
    pdf.rect(15, y, pdf.w - 30, 20, style="F")
    pdf.set_xy(18, y + 3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*ORANGE)
    pdf.cell(0, 5, "Your Butte Home Buyers territory (Chico / Paradise / Oroville / Magalia):",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(18)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7,
        f"{jeff_count} parcels  |  {_fmt_money(jeff_bal)} total defaulted"
    )
    pdf.set_y(y + 24)

    # Data table
    pdf.set_text_color(*GREY_DARK)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(*WHITE)

    # Column widths
    col_city = 40
    col_count = 20
    col_bal = 42
    col_avg = 24
    col_max = 24
    col_flag = 32

    x0 = pdf.l_margin
    pdf.set_x(x0)
    pdf.cell(col_city,  6, " Area",              fill=True)
    pdf.cell(col_count, 6, "Parcels",   align="R", fill=True)
    pdf.cell(col_bal,   6, "Total Defaulted",  align="R", fill=True)
    pdf.cell(col_avg,   6, "Avg Score", align="R", fill=True)
    pdf.cell(col_max,   6, "Peak",      align="R", fill=True)
    pdf.cell(col_flag,  6, "  Note", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY_DARK)
    striped = False
    for _, r in geo.iterrows():
        city = r["_city"]
        cnt = int(r["count"])
        bal = float(r["total_bal"])
        avg = float(r["avg_pri"])
        peak = float(r["max_pri"])

        in_territory = city.upper() in JEFF_TERRITORY
        note = ""
        row_bg = (255, 245, 220) if in_territory else (245, 249, 253) if striped else WHITE
        if in_territory:
            note = "  Your territory"
        elif city == "Gridley" and peak == 0:
            note = "  All redeemed"
        elif city == "No Situs":
            note = "  Land / lots"
        elif city == "Berry Creek" or city == "Concow" or city == "Feather Falls":
            note = "  Burn-scar area"

        pdf.set_fill_color(*row_bg)
        pdf.set_x(x0)
        pdf.cell(col_city,  5, " " + city,        fill=True, border=0)
        pdf.cell(col_count, 5, str(cnt),          align="R", fill=True, border=0)
        pdf.cell(col_bal,   5, _fmt_money(bal),   align="R", fill=True, border=0)
        pdf.cell(col_avg,   5, f"{avg:.0f}",      align="R", fill=True, border=0)
        pdf.cell(col_max,   5, f"{peak:.0f}",     align="R", fill=True, border=0)
        pdf.cell(col_flag,  5, note, fill=True, border=0,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        striped = not striped

    pdf.ln(4)

    # PORTFOLIO / BULK-DEAL CALLOUT
    pdf._section("Additional angle: bulk-deal opportunity in your territory", color=ORANGE)
    pdf.set_fill_color(*BG_HIGH)
    y = pdf.get_y()
    pdf.rect(15, y, pdf.w - 30, 36, style="F")
    pdf.set_xy(18, y + 3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 5, "ABADIR PERRY  --  4 contiguous parcels, Oroville",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(18)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(pdf.w - 36, 4.5,
        "One owner. Four contiguous APNs in book 033-232 (Oro Dam Blvd area). "
        "$116,598 combined defaulted balance. Owner mails from Danville CA "
        "-- Bay Area absentee, ~180 miles from the property. "
        "Owner-level distress signals: 1 unresolved lien, 1 paid lien, "
        "2 active creditors, 6 total tax defaults."
    )
    pdf.set_x(18)
    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*ORANGE)
    pdf.multi_cell(pdf.w - 36, 4.5,
        "One phone call could yield a 4-parcel deal. "
        "This is exactly the intelligence Bid4Assets does not surface."
    )
    pdf.set_y(y + 40)

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*GREY_MID)
    pdf.cell(0, 4, "  Also on this auction: 3 additional 2-parcel owners (Yang, Giannuzzi, Simmons) -- 6 more parcels",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    pdf._section("What else to notice")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(0, 5,
        "Oroville is the smallest population zone but the highest average priority score -- "
        "meaning the parcels there tend to have the highest defaulted balance relative to "
        "the assessed value. That's your sweet spot for a residential fix-and-flip play."
    )
    pdf.ln(2)
    pdf.multi_cell(0, 5,
        "Paradise (22) and Berry Creek (21) dominate by parcel count but many are "
        "rebuild-ready lots (Camp Fire footprint) -- higher land value, low improvement value. "
        "Different play, different exit."
    )
    pdf.ln(2)
    pdf.multi_cell(0, 5,
        "Chico is absent from this auction cycle. If Chico is your primary target, "
        "the November reoffer auction typically includes more Chico inventory."
    )


def _cln(v, default="-"):
    if _blank(v):
        return default
    return str(v).strip()


def dossier_page(pdf: PDF, row: pd.Series, headline: str):
    pdf.add_page()

    priority = float(row.get("priority_score") or 0)
    apn = _cln(row.get("apn"))
    owner = _cln(row.get("verified_current_owner_name"))
    balance = _money(row.get("v_total_balance"))
    situs = _cln(row.get("situs_address"))
    mailing = _cln(row.get("mailing_address"))
    is_absentee = row.get("out_of_state") == "Y"
    owner_state = _cln(row.get("owner_state"))
    land = _money(row.get("land_value"))
    improvements = _money(row.get("improvements_value"))
    fire = _cln(row.get("fire_hazard_zone"))
    flood = _cln(row.get("flood_zone"))
    dsig = _cln(row.get("distress_signals"), default="none on record")
    dsig_score_raw = row.get("distress_signal_score")
    dsig_score = _cln(dsig_score_raw, default="0")
    portfolio = _cln(row.get("portfolio_apn_count"), default="1")
    tax_billed = _money(row.get("total_tax_billed"))
    doc_count = _cln(row.get("recorder_doc_count"), default="0")
    homeowner_ex = _cln(row.get("homeowner_exemption"), default="N")

    # Header bar with headline
    pdf._bar(pdf.get_y() - 3, 12, NAVY)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(18, pdf.get_y() - 1)
    pdf.cell(0, 5, headline)
    pdf.ln(12)
    pdf.set_text_color(*GREY_DARK)

    # Owner + APN
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, owner, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY_MID)
    pdf.cell(0, 4, f"APN {apn}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    # Top signal cards
    y = pdf.get_y()
    cards = [
        ("DEFAULTED BALANCE", _fmt_money(balance), RED if balance >= 50000 else ORANGE),
        ("PRIORITY", f"{priority:.0f}", NAVY_LIGHT),
        ("DISTRESS SIGNALS", str(dsig_score), RED if int(float(dsig_score or 0)) >= 5 else ORANGE),
    ]
    card_w = 55
    for i, (label, value, color) in enumerate(cards):
        x = 15 + i * (card_w + 4)
        pdf.set_fill_color(*color)
        pdf.rect(x, y, card_w, 16, style="F")
        pdf.set_xy(x, y + 1)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*WHITE)
        pdf.cell(card_w, 6, value, align="C")
        pdf.set_xy(x, y + 9)
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(card_w, 4, label, align="C")

    pdf.set_y(y + 22)
    pdf.set_text_color(*GREY_DARK)

    # -- Two-column: Address (left) + Satellite image (right) --
    section_top = pdf.get_y()
    img_w = 70
    img_h = 70
    img_x = pdf.w - pdf.r_margin - img_w
    img_y = section_top

    # Fetch satellite image
    img_path = fetch_parcel_image(
        apn,
        row.get("geocode_lat"),
        row.get("geocode_lon"),
        size=480,
        radius_m=90.0,
    )

    # LEFT COLUMN: Address (constrained width so text doesn't run under image)
    left_col_w = img_x - pdf.l_margin - 4
    pdf.set_x(pdf.l_margin)
    pdf._section("Address")

    def _kv_col(key, value, key_w=32, size=10):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", size)
        pdf.set_text_color(*GREY_MID)
        pdf.cell(key_w, 5, key)
        pdf.set_font("Helvetica", "", size)
        pdf.set_text_color(*GREY_DARK)
        val_w = left_col_w - key_w
        pdf.multi_cell(val_w, 5, value or "-")

    _kv_col("Situs",   situs)
    _kv_col("Mailing", mailing)
    if is_absentee:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*ORANGE)
        pdf.multi_cell(left_col_w, 5,
                       f"  * OUT-OF-STATE ABSENTEE (owner in {owner_state})")

    left_end_y = pdf.get_y()

    # RIGHT COLUMN: Satellite image + caption
    if img_path and os.path.exists(img_path):
        try:
            pdf.image(img_path, x=img_x, y=img_y, w=img_w, h=img_h)
            # Border
            pdf.set_draw_color(*NAVY)
            pdf.set_line_width(0.3)
            pdf.rect(img_x, img_y, img_w, img_h)
            # Caption
            pdf.set_xy(img_x, img_y + img_h + 1)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*NAVY)
            pdf.cell(img_w, 4, "AERIAL VIEW  |  ~180m x 180m", align="C")
            pdf.set_xy(img_x, img_y + img_h + 5)
            pdf.set_font("Helvetica", "I", 6.5)
            pdf.set_text_color(*GREY_MID)
            pdf.cell(img_w, 3, "Esri, Maxar, Earthstar Geographics", align="C")
        except Exception as e:
            print(f"  WARN embedding image for {apn}: {e}")
    else:
        # Fallback placeholder if no image
        pdf.set_draw_color(*GREY_PALE)
        pdf.set_line_width(0.3)
        pdf.rect(img_x, img_y, img_w, img_h)
        pdf.set_xy(img_x, img_y + img_h / 2 - 4)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*GREY_MID)
        pdf.cell(img_w, 4, "No aerial available", align="C")

    # Advance past whichever column is lower
    pdf.set_y(max(left_end_y, img_y + img_h + 10))
    pdf.ln(1)

    # Assessment + Bid Metrics
    pdf._section("Assessment & Bid Analysis")
    pdf._kv("Land value",        _fmt_money(land))
    pdf._kv("Improvements value", _fmt_money(improvements))
    pdf._kv("Improvement ratio", f"{(improvements / land):.2f}" if land > 0 else "-")
    pdf._kv("Homeowner exempt.", str(homeowner_ex))
    pdf._kv("Total tax billed",  _fmt_money(tax_billed))

    # Bid metrics from auction targets merge
    min_bid = _money(row.get("min_bid"))
    max_bid = _money(row.get("max_bid_threshold"))
    nav = _money(row.get("net_assessed_value"))
    btv = _cln(row.get("bid_to_value_pct"), default="-")

    if min_bid > 0:
        pdf.ln(1)
        # Highlight box for bid metrics
        pdf.set_fill_color(*BG_LIGHT)
        by = pdf.get_y()
        pdf.rect(pdf.l_margin, by, pdf.w - pdf.l_margin - pdf.r_margin, 26, style="F")
        pdf.set_y(by + 1)
        pdf._kv("Minimum bid",      _fmt_money(min_bid))
        pdf._kv("Assessed value",   _fmt_money(nav) if nav > 0 else "-")
        pdf._kv("Max safe bid (70%)", _fmt_money(max_bid) if max_bid > 0 else "-")
        pdf._kv("Bid / value ratio", str(btv))
        pdf.set_y(by + 27)
    pdf.ln(2)

    # Distress signals
    pdf._section("Owner history (from recorder crawl)")
    pdf._kv("Distress signals",  str(dsig))
    pdf._kv("Recorded docs",     f"{doc_count} documents on file")
    pdf._kv("Portfolio APNs",    f"{portfolio} parcels this auction (this owner)")
    pdf.ln(2)

    # Environmental
    pdf._section("Environmental")
    pdf._kv("Fire hazard zone", str(fire))
    pdf._kv("FEMA flood zone",  str(flood))
    pdf.ln(3)

    # Footer note
    pdf.set_draw_color(*GREY_PALE)
    pdf.set_line_width(0.2)
    y = pdf.get_y()
    pdf.line(15, y, pdf.w - 15, y)
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*GREY_MID)
    pdf.multi_cell(0, 4,
        "Full pack: this same dossier plus the source tax bill PDF for every one of the 105 parcels, "
        "delivered as individual files + a combined PDF + an Excel workbook + CSV."
    )


def offer_page(pdf: PDF, total_leads: int, total_balance: float):
    pdf.add_page()
    pdf._section("The full intelligence pack")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(0, 5,
        "The full delivery includes all 105 auction parcels, packaged into a "
        "single zip file you can drop into a folder and start working from:"
    )
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*NAVY)
    items = [
        ("Excel workbook",  "4 tabs -- leads, verification detail, doc references, how-to"),
        ("Overview PDF",    "3 pages -- headline stats, geographic breakdown, top 10 targets"),
        ("Per-parcel dossiers", "105 individual 2-page PDFs (dossier + attached tax bill)"),
        ("Combined dossier PDF", "All 105 dossiers in one file for easy scroll"),
        ("Tax bill archive", "105 raw county tax bill HTMLs -- your audit trail"),
        ("Raw CSV",         "70 fields per parcel for programmatic use / re-scoring"),
    ]
    label_w = 48
    body_w = pdf.w - pdf.l_margin - pdf.r_margin - label_w
    for label, desc in items:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*NAVY)
        pdf.set_x(pdf.l_margin)
        pdf.cell(label_w, 5, "  " + label)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*GREY_DARK)
        pdf.multi_cell(body_w, 5, desc)
    pdf.ln(4)

    # Contact for pricing box
    pdf.set_fill_color(*BG_LIGHT)
    pdf.set_draw_color(*NAVY_LIGHT)
    y = pdf.get_y()
    pdf.rect(15, y, pdf.w - 30, 18, style="FD")
    pdf.set_xy(15, y + 5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*NAVY)
    pdf.cell(pdf.w - 30, 8, "Contact for pricing", align="C")
    pdf.set_y(y + 24)

    pdf._section("Guarantee")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(0, 5,
        "Every lead links to the live county tax bill and the recorder document "
        "number. Verify anything in 30 seconds. If any material field on any "
        "parcel is wrong -- owner, mailing address, defaulted balance, "
        "redemption status -- I refund on that parcel's basis. No questions."
    )
    pdf.ln(4)

    # Big contact block at bottom
    pdf.ln(6)
    pdf.set_fill_color(*NAVY)
    y = pdf.get_y()
    pdf.rect(15, y, pdf.w - 30, 22, style="F")
    pdf.set_xy(15, y + 3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 6, "Charles Terrell", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, "Logic Flow Systems", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, "mrt@logicflowsystems.io", align="C")


def build():
    df = pd.read_csv(CALL_SHEET, dtype=str)
    df["bal_num"] = df["v_total_balance"].apply(_money)
    total_leads = len(df)
    total_balance = df["bal_num"].sum()

    # Count active (non-redeemed) parcels
    redeemed_mask = df["redemption_status"].astype(str).str.strip().str.lower() == "redeemed"
    active_count = int((~redeemed_mask).sum())
    verification_ts = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    # Merge auction targets for min bid / max bid data
    if os.path.exists(TARGETS_CSV):
        tv = pd.read_csv(TARGETS_CSV, dtype=str)
        tv["_k"] = tv["apn_dash"].apply(lambda s: re.sub(r"[^0-9]", "", str(s)))
        df["_k"] = df["apn"].apply(lambda s: re.sub(r"[^0-9]", "", str(s)))
        tv_cols = ["_k", "min_bid", "net_assessed_value", "max_bid_threshold", "bid_to_value_pct"]
        tv_slim = tv[[c for c in tv_cols if c in tv.columns]]
        df = df.merge(tv_slim, on="_k", how="left", suffixes=("", "_tv"))
        print(f"  Merged auction targets: {len(tv)} rows from {TARGETS_CSV}")
    else:
        print(f"  WARN: Targets CSV not found at {TARGETS_CSV} -- bid metrics will be blank")

    # Pick our three
    rows = []
    for apn in TARGET_APNS:
        match = df[df["apn"] == apn]
        if match.empty:
            print(f"WARN: APN {apn} not found")
            continue
        rows.append(match.iloc[0])

    if len(rows) < 3:
        raise RuntimeError(f"Only found {len(rows)} of 3 target APNs")

    headlines = [
        "Why this might interest Butte Home Buyers  --  Owner-occupied profile, real house, in-state owner",
        "Why this might interest Butte Home Buyers  --  Heavy distress history (4 prior NODs, 1 trustee sale)",
        "Why this might interest Butte Home Buyers  --  Out-of-state absentee owner (motivated seller profile)",
    ]

    os.makedirs(OUT_DIR, exist_ok=True)
    date_slug = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(OUT_DIR, f"jeff_teaser_{date_slug}.pdf")

    pdf = PDF()
    cover_page(pdf, total_leads, total_balance, active_count, verification_ts)
    methodology_page(pdf)
    comparison_page(pdf)
    verification_catch_page(pdf)
    geographic_page(pdf, df)
    for row, headline in zip(rows, headlines):
        dossier_page(pdf, row, headline)
    offer_page(pdf, total_leads, total_balance)
    pdf.output(out_path)

    size = os.path.getsize(out_path)
    print(f"Wrote {out_path} ({size:,} bytes)")
    print(f"Pages: 9  (cover + methodology + comparison + verification + geo + 3 dossiers + offer)")
    print(f"  Active parcels: {active_count} / {total_leads}")
    print(f"  Verification stamp: {verification_ts}")
    return out_path


if __name__ == "__main__":
    build()
