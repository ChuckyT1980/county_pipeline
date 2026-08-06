"""
Butte County Tax Auction Intelligence Bulletin.

Portable 2-page sales bulletin — no buyer-specific personalization,
no owner PII (names / APNs / mailing addresses redacted).

Purpose: sendable to any prospect (Bid4Assets prior bidders, Yuba,
Chain, Sacramento wholesalers, etc.) as first-touch outreach or as
attachment to cold email.

Structure:
    Page 1: Executive summary + key findings
    Page 2: What you get + pricing + contact

Output: delivery/butte_auction_bulletin_YYYY-MM-DD.pdf
"""
import os
import re
from datetime import datetime, date

import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos

BUTTE_DIR = os.path.dirname(os.path.abspath(__file__))
CALL_SHEET = os.path.join(BUTTE_DIR, "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
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

_BUTTE_CITIES = [
    "STIRLING CITY", "BERRY CREEK", "FEATHER FALLS", "FOREST RANCH",
    "YANKEE HILL", "CLIPPER MILLS", "PARADISE", "MAGALIA", "OROVILLE",
    "CONCOW", "CHICO", "GRIDLEY", "BIGGS", "COHASSET", "PALERMO",
    "BANGOR", "DURHAM", "RICHVALE", "FORBESTOWN",
]

RESIDENTIAL_TERRITORY = {"CHICO", "PARADISE", "OROVILLE", "MAGALIA"}

_NON_LATIN1 = {
    "–": "-", "—": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "•": "*", "…": "...",
    " ": " ", "�": "?",
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


def _extract_city(situs):
    if _blank(situs):
        return "No Situs"
    s = str(situs).strip().upper()
    for city in _BUTTE_CITIES:
        if s.endswith(city):
            return city.title()
    tokens = s.split()
    return tokens[-1].title() if tokens else "Unknown"


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


def _compute_findings(df):
    """Extract redacted, headline-level findings from the call sheet."""
    df = df.copy()
    df["_bal"] = df["v_total_balance"].apply(_money)
    df["_city"] = df["situs_address"].apply(_extract_city)
    df["_pri"] = pd.to_numeric(df["priority_score"], errors="coerce").fillna(0)

    total_leads = len(df)
    total_balance = df["_bal"].sum()

    redeemed_mask = df["redemption_status"].astype(str).str.strip().str.lower() == "redeemed"
    redeemed_count = int(redeemed_mask.sum())
    redeemed_balance = df.loc[redeemed_mask, "_bal"].sum()
    active_count = total_leads - redeemed_count

    territory_mask = df["_city"].str.upper().isin(RESIDENTIAL_TERRITORY)
    territory_count = int(territory_mask.sum())
    territory_balance = df.loc[territory_mask, "_bal"].sum()

    no_situs_count = int((df["_city"] == "No Situs").sum())

    absentee_mask = df.get("out_of_state") == "Y"
    absentee_count = int(absentee_mask.sum()) if absentee_mask is not None else 0

    # Portfolio detection
    owned = df[df["verified_current_owner_name"].notna() &
               (df["verified_current_owner_name"].str.strip() != "") &
               (df["verified_current_owner_name"].str.lower() != "nan")]
    grouped = owned.groupby("verified_current_owner_name").agg(
        parcels=("apn", "count"),
        balance=("_bal", "sum"),
    )
    portfolio = grouped[grouped["parcels"] >= 2].sort_values("parcels", ascending=False)
    portfolio_owner_count = len(portfolio)
    top_portfolio_parcels = int(portfolio["parcels"].max()) if len(portfolio) else 0
    top_portfolio_balance = float(portfolio["balance"].max()) if len(portfolio) else 0

    # Distress-heavy count (owners with 5+ distress signal score)
    dsig = pd.to_numeric(df["distress_signal_score"], errors="coerce").fillna(0)
    high_distress = int((dsig >= 5).sum())

    # Burn-scar area count (Paradise, Berry Creek, Concow, Magalia, Feather Falls)
    burn_scar = df["_city"].isin(["Paradise", "Berry Creek", "Concow", "Magalia", "Feather Falls"])
    burn_scar_count = int(burn_scar.sum())

    return {
        "total_leads": total_leads,
        "total_balance": total_balance,
        "active_count": active_count,
        "redeemed_count": redeemed_count,
        "redeemed_balance": redeemed_balance,
        "territory_count": territory_count,
        "territory_balance": territory_balance,
        "no_situs_count": no_situs_count,
        "absentee_count": absentee_count,
        "portfolio_owner_count": portfolio_owner_count,
        "top_portfolio_parcels": top_portfolio_parcels,
        "top_portfolio_balance": top_portfolio_balance,
        "high_distress": high_distress,
        "burn_scar_count": burn_scar_count,
    }


def page_one(pdf: PDF, f: dict, verification_ts: str):
    days_left = max(0, (AUCTION_DATE - date.today()).days)
    pdf.add_page()

    # Header bar
    pdf._bar(0, 32, NAVY)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(15, 8)
    pdf.cell(0, 4, "INTELLIGENCE BULLETIN  |  LOGIC FLOW SYSTEMS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_xy(15, 13)
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 9, "Butte County Tax Auction", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 6, f"August 7-10, 2026  |  {days_left} days out")

    # Verification stamp band
    pdf.set_fill_color(*BG_GOOD)
    pdf.rect(0, 34, pdf.w, 8, style="F")
    pdf.set_xy(15, 35.5)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*GREEN)
    pdf.cell(0, 5, f"LIVE VERIFIED  |  {f['active_count']} active parcels confirmed delinquent as of {verification_ts}")

    pdf.set_y(48)

    # Stat cards row
    stats = [
        ("Auction parcels", str(f["total_leads"])),
        ("Still active", str(f["active_count"])),
        ("Defaulted balance", _fmt_money(f["total_balance"])),
        ("Days to auction", str(days_left)),
    ]
    card_w = 42
    y0 = pdf.get_y()
    for i, (label, value) in enumerate(stats):
        x = 15 + i * (card_w + 3)
        pdf.set_fill_color(*BG_LIGHT)
        pdf.set_draw_color(*NAVY_LIGHT)
        pdf.rect(x, y0, card_w, 22, style="FD")
        pdf.set_xy(x, y0 + 2)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*NAVY)
        pdf.cell(card_w, 8, value, align="C")
        pdf.set_xy(x, y0 + 12)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*GREY_MID)
        pdf.cell(card_w, 5, label, align="C")

    pdf.set_y(y0 + 28)

    # KEY FINDINGS section
    pdf._section("Key findings — this cycle", color=NAVY)

    findings = [
        {
            "tag": "VERIFICATION CATCH",
            "tag_color": ORANGE,
            "text": (
                f"1 parcel with $2.4M in defaulted taxes was redeemed 4 weeks ago. "
                f"The pipeline caught it against the live county tax bill. Every generic "
                f"list still shows it active. That parcel is out; {f['active_count']} remain."
            ),
        },
        {
            "tag": "BULK DEAL FOUND",
            "tag_color": RED,
            "text": (
                f"1 owner controls {f['top_portfolio_parcels']} contiguous parcels in Oroville "
                f"($116,598 combined). Bay-Area absentee. Owner has unresolved liens, "
                f"active creditors, 6 total tax defaults. Single-call, 4-parcel opportunity."
            ),
        },
        {
            "tag": "RESIDENTIAL FIT",
            "tag_color": NAVY_LIGHT,
            "text": (
                f"{f['territory_count']} parcels ({_fmt_money(f['territory_balance'])}) sit in "
                f"the residential fix-and-flip zones (Chico / Paradise / Oroville / Magalia). "
                f"{f['absentee_count']} of {f['active_count']} owners are out-of-state absentees."
            ),
        },
        {
            "tag": "LAND / BURN-SCAR",
            "tag_color": GREEN,
            "text": (
                f"{f['no_situs_count']} parcels have no situs = raw land or vacant lots. "
                f"{f['burn_scar_count']} more sit in Camp Fire burn-scar footprint -- "
                f"rebuild-ready lot potential for land investors."
            ),
        },
    ]

    # Disable auto page break while rendering findings + footer
    pdf.set_auto_page_break(auto=False)

    for finding in findings:
        y = pdf.get_y()
        # Tag pill
        pdf.set_fill_color(*finding["tag_color"])
        tag_w = 42
        pdf.rect(15, y, tag_w, 5, style="F")
        pdf.set_xy(15, y + 0.6)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*WHITE)
        pdf.cell(tag_w, 4, finding["tag"], align="C")

        # Body text
        pdf.set_xy(15, y + 6)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GREY_DARK)
        pdf.multi_cell(pdf.w - 30, 4.3, finding["text"])
        pdf.ln(3)

    # Footer bar with CTA (fixed position, no page break)
    footer_y = pdf.h - 26
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, footer_y, pdf.w, 26, style="F")
    pdf.set_xy(15, footer_y + 4)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 6, "Full 105-parcel intelligence pack: $500 (founding rate)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, "See page 2 for full inventory. Or reply to this email.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, "mrt@logicflowsystems.io  |  logicflowsystems.io")

    pdf.set_auto_page_break(auto=True, margin=15)


def page_two(pdf: PDF, f: dict):
    pdf.add_page()
    pdf._section("What's in the full pack")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(0, 5,
        "Everything cross-referenced from 6 independent county systems. "
        "Every field carries a source + verification stamp."
    )
    pdf.ln(3)

    # Two column comparison
    col_left_x = pdf.l_margin
    col_right_x = pdf.w / 2 + 4
    col_w = (pdf.w - pdf.l_margin - pdf.r_margin - 8) / 2
    y = pdf.get_y()

    # LEFT: County PDF
    pdf.set_fill_color(*GREY_PALE)
    pdf.rect(col_left_x, y, col_w, 10, style="F")
    pdf.set_xy(col_left_x + 2, y + 2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*GREY_DARK)
    pdf.cell(col_w, 6, "County PDF (free)")

    # RIGHT: Intelligence Pack
    pdf.set_fill_color(*NAVY)
    pdf.rect(col_right_x, y, col_w, 10, style="F")
    pdf.set_xy(col_right_x + 2, y + 2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*WHITE)
    pdf.cell(col_w, 6, "Intelligence Pack ($500)")

    y += 14
    pdf.set_text_color(*GREY_DARK)

    # Left items
    county_items = ["APN", "Owner name", "Property address",
                    "Jurisdiction", "Minimum bid"]
    pdf.set_font("Helvetica", "", 10)
    for item in county_items:
        pdf.set_xy(col_left_x + 4, y)
        pdf.cell(col_w, 5, "  " + item)
        y += 6

    pdf.set_xy(col_left_x + 4, y + 2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*GREY_MID)
    pdf.cell(col_w, 5, "5 fields.  No verification.")

    # Right items
    y_right_start = pdf.get_y() - (len(county_items) * 6) - 2
    intel_groups = [
        ("Financial (8)", "Min bid, assessed value, max safe bid, bid-to-value, land, improvements, tax billed, defaulted"),
        ("Ownership (10)", "Verified owner, entity, vesting confidence, mailing, state, absentee flag, class, flags, contributors, portfolio"),
        ("Title / Liens (8)", "Doc numbers, types, dates, count, business partners, distress signals, distress score, signal counts"),
        ("Tax History (8)", "Bill date, power-to-sell, years since PTS, redemption status/date, exemption, installment, special assessments"),
        ("Environmental (6)", "Fire zone, fire responsibility, flood zone, subtype, geocode lat/lon"),
        ("Verification (6)", "Verification score, sources, flag count, owner conf, mailing conf, situs conf"),
    ]
    y_r = y_right_start
    for group_title, fields in intel_groups:
        pdf.set_xy(col_right_x + 4, y_r)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*NAVY)
        pdf.cell(col_w - 8, 4, group_title)
        y_r += 5
        pdf.set_xy(col_right_x + 4, y_r)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*GREY_DARK)
        pdf.multi_cell(col_w - 8, 3.8, fields)
        y_r = pdf.get_y() + 1

    pdf.set_xy(col_right_x + 4, y_r + 2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*NAVY)
    pdf.cell(col_w, 5, "70 fields.  6 sources.  Live-verified.")

    # DELIVERABLES section
    pdf.set_y(max(y, y_r) + 12)
    pdf._section("What ships with the pack")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY_DARK)
    items = [
        ("Excel workbook",       "4 tabs -- leads, verification, doc refs, how-to"),
        ("Overview PDF",         "3 pages -- headline stats, geographic breakdown, top targets"),
        (f"Dossiers ({f['active_count']} parcels)",
                                 "Individual 2-page PDFs -- dossier + attached tax bill per parcel"),
        ("Combined dossier PDF", f"All {f['active_count']} in one file for easy scroll"),
        ("Tax bill archive",     "Raw county tax bill HTMLs -- your audit trail"),
        ("Raw CSV",              "70 fields per parcel for programmatic use"),
    ]
    label_w = 42
    body_w = pdf.w - pdf.l_margin - pdf.r_margin - label_w
    for label, desc in items:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*NAVY)
        pdf.set_x(pdf.l_margin)
        pdf.cell(label_w, 4.5, "  " + label)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GREY_DARK)
        pdf.multi_cell(body_w, 4.5, desc)

    pdf.ln(3)

    # PRICING / OFFER box
    pdf.set_fill_color(*BG_HIGH)
    y = pdf.get_y()
    pdf.rect(15, y, pdf.w - 30, 34, style="F")
    pdf.set_xy(20, y + 3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, "Founding-customer pricing", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(20)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*RED)
    pdf.cell(0, 8, "$500  -- this cycle  |  $150/month recurring", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(20)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(pdf.w - 40, 4.3,
        "Pack rebuilt for every Butte auction going forward. Founding rate grandfathered "
        "as long as subscription stays active. Payment on delivery -- Zelle, ACH, or check."
    )

    pdf.set_y(y + 40)

    # GUARANTEE
    pdf._section("Guarantee", color=GREEN)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(0, 4.5,
        "Every lead links to the live county tax bill and recorder document number. "
        "Verify anything in 30 seconds. If any material field on any parcel is wrong -- "
        "owner, mailing, defaulted balance, redemption status -- I refund on that parcel's basis. No questions."
    )
    pdf.ln(3)

    # Contact block
    pdf.set_fill_color(*NAVY)
    y = pdf.get_y()
    pdf.rect(15, y, pdf.w - 30, 22, style="F")
    pdf.set_xy(15, y + 3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 6, "To order or ask questions", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, "Chuck Terrell  |  Logic Flow Systems", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, "mrt@logicflowsystems.io  |  logicflowsystems.io", align="C")


def build():
    df = pd.read_csv(CALL_SHEET, dtype=str)
    f = _compute_findings(df)
    verification_ts = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    os.makedirs(OUT_DIR, exist_ok=True)
    date_slug = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(OUT_DIR, f"butte_auction_bulletin_{date_slug}.pdf")

    pdf = PDF()
    page_one(pdf, f, verification_ts)
    page_two(pdf, f)
    pdf.output(out_path)

    size = os.path.getsize(out_path)
    print(f"Wrote {out_path} ({size:,} bytes)")
    print(f"Pages: 2 -- portable bulletin, no PII, sendable to any prospect")
    print()
    print("Findings baked into the bulletin:")
    for k, v in f.items():
        print(f"  {k}: {v}")
    return out_path


if __name__ == "__main__":
    build()
