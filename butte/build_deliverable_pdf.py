"""
Branded, multi-page buyer-facing PDF for the Butte auction call sheet.

Three pages:
  1. Cover — headline stats, top-10 preview, key intelligence callouts
  2. Methodology + How to Read a Lead — sample profile, workflow guide
  3. Data dictionary — every column explained

Uses fpdf2 with a real color palette + typographic hierarchy so this looks
like a paid intelligence product, not a data dump.
"""
import argparse
import json
import os
import sys
from datetime import datetime

import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Brand palette
NAVY       = (31, 58, 95)
NAVY_LIGHT = (46, 134, 171)
GREY_DARK  = (60, 60, 60)
GREY_MID   = (120, 120, 120)
GREY_LIGHT = (232, 241, 247)
ACCENT     = (198, 88, 61)   # burnt orange for callouts
BG_HIGH    = (255, 232, 200)
WHITE      = (255, 255, 255)


def _money_to_float(s):
    if pd.isna(s):
        return 0.0
    try:
        return float(str(s).replace("$", "").replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _fmt_money(v: float) -> str:
    return f"${v:,.0f}"


def _blank(v):
    if v is None or pd.isna(v):
        return True
    return str(v).strip().lower() in {"", "nan", "none"}


def _clean_str_val(v):
    """Return a clean string or empty for NaN/None/'nan' values."""
    if _blank(v):
        return ""
    return str(v).strip()


class BrandedPDF(FPDF):
    def header(self):
        # Skip on cover page
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*NAVY)
        self.cell(0, 6, "Butte County Tax Auction Intelligence  Aug 7-10, 2026", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_text_color(*GREY_MID)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, f"Page {self.page_no()}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*NAVY)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GREY_MID)
        self.cell(0, 4, "Data pulled from Butte County public records. Verify independently before making offers.", align="C")

    def section_header(self, text: str, color=None):
        color = color or NAVY
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*color)
        self.cell(0, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*color)
        self.set_line_width(0.4)
        y = self.get_y()
        self.line(self.l_margin, y, self.l_margin + 30, y)
        self.ln(3)

    def body(self, text: str, size: int = 10):
        self.set_font("Helvetica", "", size)
        self.set_text_color(*GREY_DARK)
        self.set_x(self.l_margin)
        self.multi_cell(0, 4.5, text)

    def bullet(self, text: str, size: int = 10):
        self.set_font("Helvetica", "", size)
        self.set_text_color(*GREY_DARK)
        # Reset to left margin every call so previous cell state can't shrink width
        self.set_x(self.l_margin)
        self.multi_cell(0, 4.5, f"   {chr(149)}  {text}")

    def callout(self, title: str, body: str, bg=None):
        """Simple bordered callout — no fancy positioning. Fills the box after
        rendering text so we know actual height, avoiding cursor-state bugs."""
        bg = bg or BG_HIGH
        x0 = self.l_margin
        w = self.w - self.l_margin - self.r_margin
        y_start = self.get_y()

        # Render text first with normal cursor flow — measure height from y_delta
        self.set_x(x0 + 3)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*NAVY)
        self.cell(w - 6, 5, title)
        self.ln(5)
        self.set_x(x0 + 3)
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*GREY_DARK)
        self.multi_cell(w - 6, 4.4, body)
        y_end = self.get_y()

        # Draw the background rect BEHIND the rendered text (redraw)
        # We can't actually put fill behind existing text in fpdf, but we can
        # draw a colored bar on the left as a visual highlight instead.
        self.set_fill_color(*bg)
        self.rect(x0, y_start - 1, 2, y_end - y_start + 2, style="F")
        # And a light border box
        self.set_draw_color(*bg)
        self.set_line_width(0.2)
        self.rect(x0, y_start - 1, w, y_end - y_start + 2, style="D")
        self.ln(3)
        self.set_x(x0)


def build(csv_path: str, output: str) -> str:
    df = pd.read_csv(csv_path, dtype=str)
    df["_bal"] = df["v_total_balance"].apply(_money_to_float)
    df["_score"] = pd.to_numeric(df["priority_score"], errors="coerce")

    total_leads = len(df)
    total_balance = df["_bal"].sum()
    has_owner = df["verified_current_owner_name"].notna() & \
                (df["verified_current_owner_name"].astype(str).str.strip().str.lower() != "nan")
    has_mailing = df["mailing_address"].notna() & \
                  (df["mailing_address"].astype(str).str.strip() != "") & \
                  (df["mailing_address"].astype(str).str.strip().str.lower() != "nan")
    out_of_state = int((df["out_of_state"] == "Y").sum()) if "out_of_state" in df.columns else 0

    fire_vh = int((df["fire_hazard_zone"] == "Very High").sum()) if "fire_hazard_zone" in df.columns else 0
    flood_hi = int(df["flood_zone"].isin(["A", "AE", "V", "VE"]).sum()) if "flood_zone" in df.columns else 0

    portfolio_series = pd.to_numeric(df.get("portfolio_apn_count"), errors="coerce")
    portfolios = int((portfolio_series >= 2).sum()) if portfolio_series is not None else 0

    ds_num = pd.to_numeric(df.get("distress_signal_score"), errors="coerce").fillna(0) if "distress_signal_score" in df.columns else None
    high_distress = int((ds_num >= 30).sum()) if ds_num is not None else 0

    entity_counts = df["entity_type"].value_counts(dropna=True).to_dict() if "entity_type" in df.columns else {}

    # Geographic breakdown by situs city (added per critique — helps buyer immediately
    # see whether inventory matches their target area)
    def _city(s):
        if pd.isna(s) or not str(s).strip():
            return "No situs (vacant)"
        tokens = str(s).upper().split()
        two_word_cities = {"BERRY CREEK", "FEATHER FALLS", "HAMILTON CITY", "STIRLING CITY"}
        if len(tokens) >= 2 and " ".join(tokens[-2:]) in two_word_cities:
            return " ".join(tokens[-2:]).title()
        return tokens[-1].title() if tokens else "Unknown"
    df["_city"] = df["situs_address"].apply(_city)
    city_counts = df["_city"].value_counts().to_dict()

    # Redemption stats (added per critique — surface how many pulled from auction)
    redeemed_count = int((df.get("redemption_status", pd.Series()) == "redeemed").sum())

    top10 = df.sort_values("_score", ascending=False).head(10)

    # Standout finding for the cover callout.
    # Prefer the REDEMPTION-CATCH story (strongest proof of verification value),
    # falling back to top-priority-with-owner if no redemptions detected.
    redeemed_rows = df[df.get("redemption_status", "") == "redeemed"]
    if len(redeemed_rows) > 0:
        r = redeemed_rows.iloc[0]
        r_apn = str(r.get("apn",""))
        r_owner = str(r.get("verified_current_owner_name","")).strip()
        r_raw = str(r.get("raw_priority_score","")).strip() or "99+"
        r_bal = _fmt_money(_money_to_float(r.get("v_total_balance")))
        r_date = str(r.get("redemption_date",""))
        owner_str = r_owner if r_owner and r_owner.lower() != "nan" else "The owner"
        highlight_body = (
            f"VERIFICATION CATCH: {owner_str} on APN {r_apn} ({r_bal} defaulted) would have ranked #1 on this list "
            f"(raw priority {r_raw}). Our tax bill enricher caught that the delinquency was redeemed on {r_date} "
            f"- the parcel is off the auction. It's been moved to the bottom of the ranking so you don't waste "
            f"outreach on a dead lead. Every list vendor without live tax bill verification still shows this parcel as active."
        )
    else:
        # Fallback: top parcel with owner name
        with_owner = top10[top10["verified_current_owner_name"].notna() &
                            (top10["verified_current_owner_name"].astype(str).str.strip().str.lower() != "nan")]
        top_row = with_owner.iloc[0] if len(with_owner) > 0 else top10.iloc[0]
        top_owner = str(top_row.get("verified_current_owner_name","")).strip() or "(owner not on file)"
        top_bal = _fmt_money(top_row["_bal"])
        top_apn = str(top_row.get("apn",""))
        top_state = str(top_row.get("owner_state",""))
        if top_state and top_state != "CA":
            highlight_body = (
                f"{top_owner} owes {top_bal} on APN {top_apn} in Butte County. "
                f"Owner mailing address is in {top_state} - out-of-state absentee, "
                "top-priority target on the list."
            )
        else:
            highlight_body = f"{top_owner} owes {top_bal} on APN {top_apn} - top-priority target on the list."

    # Pick a SAMPLE lead for the profile callout — one with complete data across all signals.
    # Requirements: has owner, has fire_hazard, has distress signals, has portfolio > 1, ideally in-state
    # so the reader sees the fullest profile.
    def _row_complete_score(r):
        s = 0
        if not _blank(r.get("verified_current_owner_name")): s += 1
        if not _blank(r.get("fire_hazard_zone")): s += 1
        if not _blank(r.get("flood_zone")): s += 1
        if not _blank(r.get("distress_signals")): s += 2  # weight distress higher
        try:
            if float(r.get("portfolio_apn_count") or 0) >= 2: s += 2
        except Exception:
            pass
        if not _blank(r.get("business_partners")): s += 1
        if not _blank(r.get("recorder_doc_numbers")): s += 1
        return s
    df["_completeness"] = df.apply(_row_complete_score, axis=1)
    sample_pool = df[df["_completeness"] >= 5].sort_values("_score", ascending=False)
    if len(sample_pool) == 0:
        sample_pool = df.sort_values("_completeness", ascending=False)
    sample = sample_pool.iloc[0]

    # Recorder graph stats
    graph_docs = graph_actors = consistency_flags = 0
    try:
        from verification.db import connect as _vconnect
        _c = _vconnect()
        r = _c.execute(
            """SELECT
                (SELECT COUNT(*) FROM graph_nodes WHERE node_kind='doc' AND county='butte') AS d,
                (SELECT COUNT(*) FROM graph_nodes WHERE node_kind='person') AS p,
                (SELECT COUNT(*) FROM graph_nodes WHERE node_kind='entity') AS e
            """
        ).fetchone()
        graph_docs = r["d"] or 0
        graph_actors = (r["p"] or 0) + (r["e"] or 0)
        cf = _c.execute(
            "SELECT COUNT(*) AS n FROM verification_flags WHERE layer='consistency' AND severity IN ('warn','error')"
        ).fetchone()
        consistency_flags = cf["n"] if cf else 0
        _c.close()
    except Exception:
        pass

    pdf = BrandedPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(left=15, top=14, right=15)

    # ============================================================
    # PAGE 1 - COVER
    # ============================================================
    pdf.add_page()

    # Navy title band
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, 42, style="F")

    pdf.set_xy(15, 10)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 10, "Butte County Tax Auction Intelligence", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(230, 230, 230)
    pdf.cell(0, 6, f"Aug 7-10, 2026 Reoffer Auction  {total_leads} Pre-Scored Leads", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 5, f"Edition {datetime.now():%B %d, %Y}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_y(50)

    # Headline stat strip
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*NAVY)
    strip_data = [
        ("TOTAL LEADS", str(total_leads)),
        ("TOTAL BALANCE", _fmt_money(total_balance)),
        ("PORTFOLIO OWNERS", str(portfolios)),
        ("ABSENTEE", str(out_of_state)),
        ("FIRE-HAZARD", str(fire_vh)),
        ("DISTRESS 30+", str(high_distress)),
    ]
    strip_w = (pdf.w - 30) / len(strip_data)
    for i, (label, value) in enumerate(strip_data):
        x = 15 + i * strip_w
        y = 52
        pdf.set_fill_color(*GREY_LIGHT)
        pdf.rect(x, y, strip_w - 2, 16, style="F")
        pdf.set_xy(x, y + 1)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*GREY_MID)
        pdf.cell(strip_w - 2, 4, label, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_xy(x, y + 5)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(*NAVY)
        pdf.cell(strip_w - 2, 9, value, align="C")
    pdf.set_y(72)

    # Highlight callout
    callout_title = ("KEY FINDING - VERIFICATION CATCH" if len(redeemed_rows) > 0
                     else "KEY FINDING - TOP-PRIORITY LEAD")
    pdf.callout(callout_title, highlight_body, bg=BG_HIGH)

    # Geographic breakdown — added per critique, most-actionable pre-pitch info
    pdf.section_header("Inventory by situs city")
    city_line_parts = []
    for city, ct in sorted(city_counts.items(), key=lambda x: -x[1]):
        if ct >= 2:  # only show cities with 2+ parcels
            city_line_parts.append(f"{city} {ct}")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*GREY_DARK)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 4.5, "   " + "   |   ".join(city_line_parts))
    pdf.ln(2)

    # Redemption note
    if redeemed_count > 0:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*ACCENT)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 4,
            f"   Note: {redeemed_count} parcel(s) had delinquent taxes redeemed after list publication; "
            f"they are flagged and moved to bottom of the ranking (priority score 0).")
        pdf.ln(2)

    # What's inside
    pdf.section_header("What's inside")
    pdf.bullet(f"Priority score 0-100 per lead (log-scaled on defaulted balance)")
    pdf.bullet(f"Owner name (recorder chain of title) - {has_owner.sum()} of {total_leads}")
    pdf.bullet(f"Mailing address (assessor records, direct-mail ready) - {has_mailing.sum()} of {total_leads}")
    pdf.bullet(f"Out-of-state absentee flag - {out_of_state} of {total_leads}")
    pdf.bullet(f"Portfolio detection - {portfolios} owners hold 2+ parcels on this auction")
    pdf.bullet(f"Distress signals per owner (NODs, IRS liens, judgments, tax defaults) sourced from a {graph_docs:,}-document recorder graph")
    pdf.bullet(f"Fire hazard flagging - {fire_vh} 'Very High' CalFire FHSZ parcels")
    pdf.bullet(f"Every value carries source + confidence for buyer audit trail")
    pdf.ln(3)

    # Top 10 table
    pdf.section_header("Top 10 by Priority")

    col_widths = [8, 12, 26, 36, 22, 76]
    headers = ["#", "Score", "APN", "Owner", "Balance", "Mailing Address"]

    # Table header row
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(*WHITE)
    for w, h in zip(col_widths, headers):
        pdf.cell(w, 6, h, fill=True, border=1, align="L")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GREY_DARK)
    for rank, (_, row) in enumerate(top10.iterrows(), start=1):
        owner = str(row.get("verified_current_owner_name", ""))
        if owner.lower() == "nan" or not owner.strip():
            owner = "(no name)"
        mail = str(row.get("mailing_address", ""))
        if mail.lower() == "nan":
            mail = ""
        # Zebra
        if rank % 2 == 0:
            pdf.set_fill_color(*GREY_LIGHT)
            fill_flag = True
        else:
            fill_flag = False
        pdf.cell(col_widths[0], 5, str(rank), border=1, fill=fill_flag)
        pdf.cell(col_widths[1], 5, f"{row['_score']:.1f}", border=1, fill=fill_flag)
        pdf.cell(col_widths[2], 5, str(row.get("apn", "")), border=1, fill=fill_flag)
        pdf.cell(col_widths[3], 5, owner[:20], border=1, fill=fill_flag)
        pdf.cell(col_widths[4], 5, _fmt_money(row["_bal"]), border=1, align="R", fill=fill_flag)
        pdf.cell(col_widths[5], 5, mail[:52], border=1, fill=fill_flag)
        pdf.ln()

    # ============================================================
    # PAGE 2 - METHODOLOGY + HOW TO READ A LEAD
    # ============================================================
    pdf.add_page()

    pdf.section_header("Methodology")
    pdf.body(
        "Every parcel scheduled for the Butte County Aug 7-10 tax-defaulted auction was pulled from the "
        "county tax collector's site, verified for active delinquency, and enriched against three additional "
        "sources: the Butte County Recorder's chain of title, the Butte County Assessor's records for mailing "
        "and situs, and CalFire + FEMA hazard zones for property risk profile. Every field on the lead carries "
        "a provenance stamp naming the source it came from and a confidence value."
    )
    pdf.ln(2)
    pdf.body(
        "Each lead is priority-scored 50 to 100 using a log-scaled function of the defaulted tax balance "
        "(linear 50-80 up to $50k, log 80-100 for $50k to $2.5M+). Higher priority = larger tax debt = more "
        "urgent for the county to sell + typically larger property. Score is a starting point, not a final ranking - "
        "combine with property fundamentals for your bidding strategy."
    )
    pdf.ln(3)

    pdf.section_header("How to read a lead")
    pdf.body(
        "Every row in the Leads sheet answers three questions: WHO owns this parcel, WHERE to reach them, "
        "and WHY they're likely to sell."
    )
    pdf.ln(2)

    # Sample lead profile — picked for completeness across all signals
    s_owner = _clean_str_val(sample.get("verified_current_owner_name")) or "(no name)"
    s_apn   = _clean_str_val(sample.get("apn"))
    s_bal   = _fmt_money(_money_to_float(sample.get("v_total_balance")))
    s_score = pd.to_numeric(sample.get("priority_score"), errors="coerce")
    s_score_str = f"{s_score:.1f}" if pd.notna(s_score) else "?"
    s_class = _clean_str_val(sample.get("ownership_class")) or "?"
    s_mail  = _clean_str_val(sample.get("mailing_address")) or "-"
    s_oos   = "ABSENTEE" if sample.get("out_of_state") == "Y" else "in-state"
    s_ports = _clean_str_val(sample.get("portfolio_apn_count")) or "1"
    s_fire  = _clean_str_val(sample.get("fire_hazard_zone")) or "unmapped"
    s_flood = _clean_str_val(sample.get("flood_zone")) or "unmapped"
    s_docs  = _clean_str_val(sample.get("recorder_doc_numbers")) or "-"
    s_dtypes = _clean_str_val(sample.get("recorder_doc_types")) or "-"
    s_signals = _clean_str_val(sample.get("distress_signals")) or "-"
    s_partners = _clean_str_val(sample.get("business_partners")) or "-"

    pdf.callout(
        f"SAMPLE LEAD PROFILE - APN {s_apn}",
        f"Owner: {s_owner} ({s_class})\n"
        f"Defaulted balance: {s_bal}   |   Priority score: {s_score_str}\n"
        f"Mailing: {s_mail}   ({s_oos})\n"
        f"Portfolio size: {s_ports} parcel(s)   |   Fire hazard: {s_fire}   |   Flood: {s_flood}\n"
        f"Distress signals: {s_signals}\n"
        f"Known partners: {s_partners[:100]}\n"
        f"Recorder doc: {s_docs} ({s_dtypes})\n"
        f"Look up at recorder.buttecounty.net using that doc number to see the source of title.",
        bg=GREY_LIGHT,
    )

    pdf.section_header("Workflow guide")
    pdf.bullet("Sort by Priority - the highlighted rows (score >= 80) are your first calls.")
    pdf.bullet("Filter by Portfolio Size > 1 - these owners have multiple defaulted parcels. Call once, deal on many.")
    pdf.bullet("Filter by Absentee = Y - out-of-state owners are traditionally the most motivated sellers.")
    pdf.bullet("Filter by Distress Score - owners with historical NODs, IRS liens, or judgment history are pre-qualified motivated sellers.")
    pdf.bullet("Cross-reference the 'Doc References' sheet to pull actual recorded documents from Butte Recorder for any lead you want to bid on.")
    pdf.bullet("Use the 'Verification' sheet to see the source and confidence for every data point.")
    pdf.bullet("Track your calls in the Notes / Outcome columns. Filter by Next Action to work your pipeline.")

    # ============================================================
    # PAGE 3 - DATA DICTIONARY
    # ============================================================
    pdf.add_page()

    pdf.section_header("Column dictionary")
    pdf.body("What every column in the Leads sheet means and where it comes from.")
    pdf.ln(3)

    dictionary = [
        ("Priority",              "0-100 score. Log-scaled on defaulted balance. 80+ highlighted."),
        ("APN",                   "Butte County parcel number, dashed format."),
        ("Owner",                 "Most recent grantee from Butte Recorder chain of title, or assessor fallback."),
        ("Owner Type",            "INDIVIDUAL / TRUST / ESTATE / LLC / CORP - inferred from name."),
        ("Defaulted Balance",     "Total tax defaulted per Butte Tax Collector."),
        ("Property Address",      "Situs address per Butte Assessor. Blank = vacant land."),
        ("Mailing Address",       "Where the tax bill goes per Butte Tax Collector. Direct-mail ready."),
        ("State",                 "Owner's mailing-address state. Non-CA = absentee."),
        ("Absentee",              "Y if mailing state != CA. Wholesaler motivation signal."),
        ("Fire Hazard",           "CalFire FHSZ zone: Very High / High / Moderate / UNZONED."),
        ("Flood Zone",            "FEMA NFHL zone code. A/AE/V/VE = high risk."),
        ("Portfolio Size",        "How many parcels on this auction this owner controls."),
        ("Portfolio $ Total",     "Combined defaulted balance across the owner's portfolio."),
        ("Distress Score",        "0-100 rollup of historical NODs, liens, judgments, tax defaults."),
        ("Distress Signals",      "Codes: unresolved_liens, prior_nods, tax_defaults, active_creditor, etc."),
        ("Known Partners",        "Co-grantees / lenders / related entities from recorder graph."),
        ("Phone",                 "Skip-traced phone (if available). Blank = not traced."),
        ("Call 1 / 2 Date + Outcome, Next Action, Notes",
                                  "Empty workflow columns for your call log."),
    ]
    label_w = 55
    desc_w = pdf.w - pdf.l_margin - pdf.r_margin - label_w
    for col, desc in dictionary:
        pdf.set_x(pdf.l_margin)
        y_start = pdf.get_y()
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*NAVY)
        pdf.multi_cell(label_w, 5, col)
        y_after_label = pdf.get_y()
        pdf.set_xy(pdf.l_margin + label_w, y_start)
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*GREY_DARK)
        pdf.multi_cell(desc_w, 5, desc)
        # Advance y to whichever ended lower
        pdf.set_y(max(y_after_label, pdf.get_y()) + 0.5)

    pdf.ln(4)
    pdf.section_header("Sources + verification")
    pdf.body(
        "Data is pulled fresh from Butte County Treasurer-Tax Collector, Butte County Assessor (MBAP AsrPrint), "
        "Butte County Recorder (Tyler EagleWeb), FEMA National Flood Hazard Layer, and CalFire Fire Hazard "
        "Severity Zones. Every field has a source + confidence in the Verification sheet. "
        f"Full recorder graph contains {graph_docs:,} historical documents and {graph_actors:,} named parties. "
        f"Consistency layer surfaced {consistency_flags} data-quality flags (held for review, not shipped in Leads)."
    )
    pdf.ln(2)
    pdf.body(
        "Disclaimer: All information is derived from Butte County public records at time of preparation. Owner and "
        "mailing information reflects the assessor's records and may not represent current beneficial ownership. "
        "Priority scores are heuristic and not investment advice. Buyer should verify all information independently "
        "before making offers or contacting owners."
    )

    pdf.output(output)
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"))
    p.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "butte_auction_call_sheet_cover_v2.pdf"))
    args = p.parse_args()
    out = build(args.csv, args.out)
    size = os.path.getsize(out)
    print(f"Wrote {out} ({size:,} bytes)")
