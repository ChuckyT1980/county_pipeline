"""
Per-parcel dossier PDF generator.

Produces one 1-page branded PDF per parcel, saved into
delivery/butte_auction_YYYY-MM-DD/dossiers/<rank>_<score>_<APN>_<owner>.pdf.
Filenames sort in priority order so a buyer scrolling the folder sees the
top targets first.

Also produces a single combined all_dossiers.pdf (105 pages) for easy
attach-to-email or print.

Each dossier is a lead-agent workbook — everything they need for one
phone call, laid out cleanly.
"""
import argparse
import os
import re
from datetime import datetime

import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from fetch_parcel_images import fetch as fetch_parcel_image


# Brand palette
NAVY       = (31, 58, 95)
NAVY_LIGHT = (46, 134, 171)
GREY_DARK  = (60, 60, 60)
GREY_MID   = (120, 120, 120)
GREY_PALE  = (200, 200, 200)
BG_LIGHT   = (232, 241, 247)
BG_HIGH    = (255, 232, 200)   # cream, for callouts + top-priority accents
BG_WARN    = (255, 210, 180)   # peach, for warnings
BG_GOOD    = (210, 240, 210)   # pale green
RED        = (192, 60, 60)
GREEN      = (60, 140, 80)
ORANGE     = (210, 130, 40)
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


_NON_LATIN1 = {
    "–": "-",    # en dash
    "—": "-",    # em dash
    "‘": "'",    # left single quote
    "’": "'",    # right single quote
    "“": '"',    # left double quote
    "”": '"',    # right double quote
    "•": "*",    # bullet (already used elsewhere as chr(149))
    "…": "...",  # ellipsis
    " ": " ",    # non-breaking space
    "�": "?",    # replacement char (from encoding damage)
}


def _s(v):
    """Clean-string: empty for nan/None, else stripped ASCII-safe str.
    fpdf's built-in Helvetica is Latin-1 only, so we strip anything outside."""
    if _blank(v):
        return ""
    s = str(v).strip()
    # Replace known problematic chars
    for bad, good in _NON_LATIN1.items():
        if bad in s:
            s = s.replace(bad, good)
    # Force Latin-1: any remaining non-encodable chars become "?"
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _priority_color(score: float) -> tuple:
    """Color for priority badge — higher priority = warmer color."""
    if score >= 80:
        return (192, 60, 60)      # deep red
    if score >= 65:
        return (210, 130, 40)     # orange
    if score >= 55:
        return (200, 170, 60)     # yellow-gold
    return (100, 130, 90)         # muted olive-green


def _sanitize_filename(text: str, max_len: int = 40) -> str:
    """Make text filesystem-safe."""
    s = re.sub(r"[^\w\s-]", "", text or "").strip()
    s = re.sub(r"[\s]+", "_", s)
    return s[:max_len] or "UNKNOWN"


def _latin1_safe(text):
    """Force any string into Latin-1-encodable form for fpdf's built-in Helvetica."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    for bad, good in _NON_LATIN1.items():
        if bad in text:
            text = text.replace(bad, good)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class DossierPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.set_auto_page_break(auto=True, margin=12)
        self.set_margins(left=14, top=12, right=14)

    def cell(self, w=None, h=None, text="", *args, **kwargs):
        return super().cell(w, h, _latin1_safe(text), *args, **kwargs)

    def multi_cell(self, w, h=None, text="", *args, **kwargs):
        return super().multi_cell(w, h, _latin1_safe(text), *args, **kwargs)

    def _bar(self, y: float, height: float, color: tuple):
        self.set_fill_color(*color)
        self.rect(0, y, self.w, height, style="F")

    def _pill(self, x: float, y: float, w: float, h: float, text: str,
              bg: tuple, fg=(255, 255, 255), size=8):
        self.set_fill_color(*bg)
        self.set_text_color(*fg)
        self.set_font("Helvetica", "B", size)
        # Rounded-ish rectangle (fpdf doesn't do true rounded, but a filled rect works)
        self.rect(x, y, w, h, style="F")
        self.set_xy(x, y + (h - size * 0.35) / 2)
        self.cell(w, size * 0.4, text, align="C")

    def _section_header(self, text: str, color=None):
        color = color or NAVY
        self.set_text_color(*color)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        y = self.get_y()
        self.set_draw_color(*color)
        self.set_line_width(0.3)
        self.line(self.l_margin, y, self.l_margin + 22, y)
        self.ln(1.5)

    def _kv(self, key: str, value: str, key_w: float = 34, size: int = 9,
            col_x: float | None = None, col_w: float | None = None):
        """Key/value row inside a column bounded by col_x + col_w."""
        col_x = col_x if col_x is not None else self.l_margin
        col_w = col_w if col_w is not None else (self.w - self.l_margin - self.r_margin)
        self.set_x(col_x)
        self.set_font("Helvetica", "B", size)
        self.set_text_color(*GREY_MID)
        self.cell(key_w, 4.5, key)
        self.set_font("Helvetica", "", size)
        self.set_text_color(*GREY_DARK)
        # Constrain value to remaining column width (no page-wide overflow)
        val_w = col_w - key_w
        # Use single-line cell then advance to next line
        self.cell(val_w, 4.5, value or "-", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(col_x)  # reset for next row in this column

    def _kv_multi(self, key: str, value: str, key_w: float = 34, size: int = 9,
                  col_x: float | None = None, col_w: float | None = None):
        """Same as _kv but wraps long values inside the same column bounds."""
        col_x = col_x if col_x is not None else self.l_margin
        col_w = col_w if col_w is not None else (self.w - self.l_margin - self.r_margin)
        self.set_x(col_x)
        self.set_font("Helvetica", "B", size)
        self.set_text_color(*GREY_MID)
        self.cell(key_w, 4.5, key)
        self.set_font("Helvetica", "", size)
        self.set_text_color(*GREY_DARK)
        self.set_x(col_x + key_w)
        self.multi_cell(col_w - key_w, 4.5, value or "-")
        self.set_x(col_x)  # reset for next row in this column


def build_dossier(pdf: DossierPDF, row: dict, rank: int, total: int) -> None:
    """Render one parcel to a fresh page."""
    pdf.add_page()

    priority = float(row.get("priority_score") or 0)
    apn = _s(row.get("apn"))
    owner = _s(row.get("verified_current_owner_name")) or "(no owner name)"
    ownership_class = _s(row.get("ownership_class")) or "UNKNOWN"
    balance = _money_to_float(row.get("v_total_balance"))
    situs = _s(row.get("situs_address")) or "(vacant / no situs)"
    mailing = _s(row.get("mailing_address")) or "-"
    owner_state = _s(row.get("owner_state"))
    is_absentee = row.get("out_of_state") == "Y"
    fire_zone = _s(row.get("fire_hazard_zone")) or "unmapped"
    flood_zone = _s(row.get("flood_zone")) or "unmapped"
    fire_ra = _s(row.get("fire_responsibility_area"))
    def _int_or(v, default=0):
        n = pd.to_numeric(v, errors="coerce")
        if pd.isna(n):
            return default
        try:
            return int(n)
        except (ValueError, TypeError):
            return default
    portfolio_count = _int_or(row.get("portfolio_apn_count"), 1)
    portfolio_balance = _money_to_float(row.get("portfolio_apn_balance"))
    portfolio_sibs = _s(row.get("portfolio_sibling_apns"))
    distress_score = _int_or(row.get("distress_signal_score"), 0)
    distress_signals = _s(row.get("distress_signals"))
    partners = _s(row.get("business_partners"))
    doc_numbers = _s(row.get("recorder_doc_numbers"))
    doc_types = _s(row.get("recorder_doc_types"))
    doc_dates = _s(row.get("recorder_doc_dates"))
    ownership_conf = _s(row.get("ownership_confidence"))
    verification_score = _s(row.get("verification_score"))
    owner_name_src = _s(row.get("owner_name_source"))
    mailing_src = _s(row.get("mailing_address_source"))
    situs_src = _s(row.get("situs_address_source"))

    # Tax bill data (added post-tax-bill-enrichment)
    redemption_status = _s(row.get("redemption_status"))
    redemption_date = _s(row.get("redemption_date"))
    power_to_sell_date = _s(row.get("power_to_sell_date"))
    years_pts = _int_or(row.get("years_since_power_to_sell"), 0)
    total_tax_billed = _money_to_float(row.get("total_tax_billed"))
    land_value = _money_to_float(row.get("land_value"))
    improvements_value = _money_to_float(row.get("improvements_value"))
    net_taxable_value = _money_to_float(row.get("net_taxable_value"))
    hox = _s(row.get("homeowner_exemption"))
    installment_active = _s(row.get("installment_plan_active"))
    special_assessments_total = _money_to_float(row.get("special_assessments_total"))
    original_bill_date = _s(row.get("original_bill_date"))

    # ── Header band ──────────────────────────────────────────────────
    pdf._bar(0, 26, NAVY)

    # Priority score badge (top-left of navy band)
    prio_color = _priority_color(priority)
    pdf.set_fill_color(*prio_color)
    pdf.rect(14, 5, 26, 16, style="F")
    pdf.set_xy(14, 5)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(26, 3.5, "PRIORITY", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(26, 9, f"{priority:.1f}", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 6.5)
    pdf.cell(26, 3, f"rank {rank} of {total}", align="C")

    # Title + APN + owner
    pdf.set_xy(44, 6)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 5, f"APN  {apn}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(44)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 5, owner[:70], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(44)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(220, 230, 240)
    pdf.cell(0, 4, "Butte County Aug 7-10, 2026 Tax Auction", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Pill row: ownership class, absentee, fire, portfolio (top-right of band)
    pdf.set_xy(0, 5)
    pill_x = pdf.w - 14
    pills = []
    pills.append((ownership_class, NAVY_LIGHT))
    if is_absentee:
        pills.append((f"ABSENTEE {owner_state}", RED))
    if fire_zone in ("Very High", "High"):
        pills.append((f"FIRE {fire_zone.upper()}", RED))
    elif fire_zone == "Moderate":
        pills.append((f"FIRE MOD", ORANGE))
    if portfolio_count >= 2:
        pills.append((f"PORTFOLIO {portfolio_count}x", ORANGE))
    if distress_score >= 30:
        pills.append((f"DISTRESS {distress_score}", RED))

    # Right-align pills in the navy band
    pill_h = 5
    pill_gap = 1.5
    total_w = 0
    pill_widths = []
    for text, _ in pills:
        # Estimate width: char count * 1.8 + padding
        w = max(16, len(text) * 1.7 + 4)
        pill_widths.append(w)
        total_w += w + pill_gap
    total_w -= pill_gap
    px = pdf.w - 14 - total_w
    for (text, color), w in zip(pills, pill_widths):
        pdf._pill(px, 6, w, pill_h, text, bg=color, fg=WHITE, size=7)
        px += w + pill_gap

    pdf.set_y(29)

    # ── Aerial image (top-right) ─────────────────────────────────────
    aerial_w = 42
    aerial_h = 42
    aerial_x = pdf.w - 14 - aerial_w
    aerial_y = 29
    aerial_path = fetch_parcel_image(
        apn,
        row.get("geocode_lat"),
        row.get("geocode_lon"),
        size=480,
        radius_m=90.0,
    )

    # ── Row: TAX STATUS callout (narrower to leave room for image) ───
    tax_w = aerial_x - 14 - 3   # leave 3mm gap before image
    pdf.set_fill_color(*BG_HIGH)
    pdf.rect(14, 29, tax_w, 15, style="F")
    pdf.set_xy(17, 30)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*NAVY)
    pdf.cell(60, 4.5, "DEFAULTED TAX BALANCE")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GREY_MID)
    pdf.cell(0, 4.5, "  |  from Butte County Tax Collector", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(17)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*NAVY)
    pdf.cell(80, 8, _fmt_money(balance))
    if portfolio_count >= 2:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*ORANGE)
        pdf.cell(0, 8, f"    portfolio total: {_fmt_money(portfolio_balance)}   ({portfolio_count} parcels)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.ln(8)

    # Render aerial image (or placeholder) on the right
    if aerial_path and os.path.exists(aerial_path):
        try:
            pdf.image(aerial_path, x=aerial_x, y=aerial_y, w=aerial_w, h=aerial_h)
            pdf.set_draw_color(*NAVY)
            pdf.set_line_width(0.3)
            pdf.rect(aerial_x, aerial_y, aerial_w, aerial_h)
            # Caption
            pdf.set_xy(aerial_x, aerial_y + aerial_h + 0.5)
            pdf.set_font("Helvetica", "B", 6.5)
            pdf.set_text_color(*NAVY)
            pdf.cell(aerial_w, 3, "AERIAL - ESRI / MAXAR", align="C")
        except Exception as e:
            print(f"  WARN aerial embed {apn}: {e}")
    else:
        pdf.set_draw_color(*GREY_PALE)
        pdf.set_line_width(0.2)
        pdf.rect(aerial_x, aerial_y, aerial_w, aerial_h)
        pdf.set_xy(aerial_x, aerial_y + aerial_h / 2 - 3)
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(*GREY_MID)
        pdf.cell(aerial_w, 3, "No aerial", align="C")
        pdf.set_xy(aerial_x, aerial_y + aerial_h / 2)
        pdf.cell(aerial_w, 3, "(no geocode)", align="C")

    # Skip past whichever ends lower — image bottom (+ caption) or callout bottom (44)
    pdf.set_y(max(48, aerial_y + aerial_h + 5))

    # ── Two-column body ──────────────────────────────────────────────
    body_y = pdf.get_y()
    col_w = (pdf.w - 28 - 6) / 2   # 6mm gutter
    col1_x = 14
    col2_x = 14 + col_w + 6

    # LEFT COLUMN: PROPERTY + OWNER
    pdf.set_xy(col1_x, body_y)
    # Section header respects column start
    pdf.set_x(col1_x)
    pdf._section_header("PROPERTY")
    pdf._kv_multi("Situs", situs, key_w=22, col_x=col1_x, col_w=col_w)
    pdf._kv("Fire hazard", f"{fire_zone}" + (f" ({fire_ra})" if fire_ra else ""),
            key_w=22, col_x=col1_x, col_w=col_w)
    pdf._kv("Flood zone", flood_zone, key_w=22, col_x=col1_x, col_w=col_w)

    pdf.ln(2)
    pdf.set_x(col1_x)
    pdf._section_header("OWNER")
    pdf._kv_multi("Name", owner, key_w=22, col_x=col1_x, col_w=col_w)
    pdf._kv("Type", ownership_class, key_w=22, col_x=col1_x, col_w=col_w)
    pdf._kv_multi("Mailing", mailing, key_w=22, col_x=col1_x, col_w=col_w)
    if is_absentee:
        pdf._kv("Absentee", f"YES ({owner_state} - out-of-state)", key_w=22, col_x=col1_x, col_w=col_w)
    else:
        pdf._kv("Absentee", f"no ({owner_state or 'CA'})", key_w=22, col_x=col1_x, col_w=col_w)
    if partners:
        pdf._kv_multi("Partners", partners.replace("|", " | "), key_w=22, col_x=col1_x, col_w=col_w)

    left_end_y = pdf.get_y()

    # RIGHT COLUMN: DISTRESS + RECORDER
    pdf.set_xy(col2_x, body_y)
    pdf._section_header("DISTRESS PROFILE")
    pdf._kv("Distress score", f"{distress_score} of 100", key_w=32, col_x=col2_x, col_w=col_w)
    if distress_signals:
        pdf._kv_multi("Signals", distress_signals.replace(",", ", "),
                      key_w=32, col_x=col2_x, col_w=col_w)
    else:
        pdf._kv("Signals", "none in graph", key_w=32, col_x=col2_x, col_w=col_w)

    pdf.ln(2)
    pdf.set_x(col2_x)
    pdf._section_header("RECORDER DOCUMENT(S)")
    if doc_numbers:
        pdf._kv_multi("Doc number", doc_numbers.replace("|", ", "),
                      key_w=32, col_x=col2_x, col_w=col_w)
        pdf._kv_multi("Type", doc_types.replace("|", ", "),
                      key_w=32, col_x=col2_x, col_w=col_w)
        pdf._kv_multi("Recorded", doc_dates.replace("|", ", "),
                      key_w=32, col_x=col2_x, col_w=col_w)
    else:
        pdf.set_x(col2_x)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*GREY_MID)
        pdf.multi_cell(col_w, 4.5, "No recorder doc linked to this APN. Owner name may be from assessor only.")

    if portfolio_count >= 2 and portfolio_sibs:
        pdf.ln(1)
        pdf.set_x(col2_x)
        pdf._section_header("PORTFOLIO SIBLINGS")
        pdf.set_x(col2_x)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*GREY_DARK)
        pdf.multi_cell(col_w, 4, "Owner also holds these other auction parcels:\n" + portfolio_sibs.replace("|", "\n"))

    right_end_y = pdf.get_y()

    # Skip past the deeper column
    pdf.set_y(max(left_end_y, right_end_y) + 3)

    # ── Tax Bill section (spans full width, added after tax bill enrichment) ──
    has_tax_bill = any([total_tax_billed, land_value, redemption_status, power_to_sell_date])
    if has_tax_bill:
        # If REDEEMED — prominent red warning banner FIRST
        if redemption_status == "redeemed":
            y = pdf.get_y()
            pdf.set_fill_color(*RED)
            pdf.rect(14, y, pdf.w - 28, 8, style="F")
            pdf.set_xy(17, y + 1.5)
            pdf.set_text_color(*WHITE)
            pdf.set_font("Helvetica", "B", 10)
            msg = f"WARNING: DELINQUENT TAXES REDEEMED {redemption_date} - PARCEL MAY NO LONGER BE ON AUCTION"
            pdf.cell(0, 5, msg)
            pdf.set_y(y + 10)

        pdf.set_x(14)
        pdf._section_header("TAX BILL")
        # Two mini-columns inside the tax bill section
        tb_col1_x = 14
        tb_col2_x = 14 + col_w + 6

        y_start = pdf.get_y()
        pdf.set_xy(tb_col1_x, y_start)
        pdf._kv("Total tax billed", _fmt_money(total_tax_billed) if total_tax_billed else "-",
                key_w=42, col_x=tb_col1_x, col_w=col_w)
        pdf._kv("Land value", _fmt_money(land_value) if land_value else "-",
                key_w=42, col_x=tb_col1_x, col_w=col_w)
        pdf._kv("Improvements value", _fmt_money(improvements_value) if improvements_value else "-",
                key_w=42, col_x=tb_col1_x, col_w=col_w)
        pdf._kv("Net taxable value", _fmt_money(net_taxable_value) if net_taxable_value else "-",
                key_w=42, col_x=tb_col1_x, col_w=col_w)
        left_bottom = pdf.get_y()

        pdf.set_xy(tb_col2_x, y_start)
        redemption_display = "Redeemed " + redemption_date if redemption_status == "redeemed" \
                             else "Still delinquent" if redemption_status == "still_delinquent" \
                             else "-"
        pdf._kv("Redemption status", redemption_display,
                key_w=42, col_x=tb_col2_x, col_w=col_w)
        pts_display = f"{power_to_sell_date} ({years_pts}y ago)" if power_to_sell_date and years_pts else power_to_sell_date or "-"
        pdf._kv("Power to Sell dated", pts_display,
                key_w=42, col_x=tb_col2_x, col_w=col_w)
        pdf._kv("Installment plan",
                "ACTIVE" if installment_active == "Y" else "no",
                key_w=42, col_x=tb_col2_x, col_w=col_w)
        pdf._kv("Homeowner exemption",
                "YES (owner-occupied)" if hox == "Y" else "no",
                key_w=42, col_x=tb_col2_x, col_w=col_w)
        if special_assessments_total and special_assessments_total > 0:
            pdf._kv("Special assessments", _fmt_money(special_assessments_total) + "/yr",
                    key_w=42, col_x=tb_col2_x, col_w=col_w)
        right_bottom = pdf.get_y()

        pdf.set_y(max(left_bottom, right_bottom) + 2)

    # ── Verification stamp (footer strip) ────────────────────────────
    stamp_y = pdf.get_y()
    if stamp_y < pdf.h - 30:
        pdf.set_fill_color(*BG_LIGHT)
        pdf.rect(14, stamp_y, pdf.w - 28, 20, style="F")
        pdf.set_xy(17, stamp_y + 1.5)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 4.5, "VERIFICATION", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(17)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*GREY_DARK)
        parts = []
        if verification_score:
            parts.append(f"Data completeness: {verification_score}%")
        if ownership_conf:
            parts.append(f"Ownership confidence: {ownership_conf}")
        if owner_name_src:
            parts.append(f"Owner name source: {owner_name_src.replace('_', ' ')}")
        if mailing_src:
            parts.append(f"Mailing source: {mailing_src.replace('_', ' ')}")
        pdf.multi_cell(pdf.w - 34, 4, "   |   ".join(parts) if parts else "-")

        # Lookup instruction — includes recorder + tax bill URLs
        pdf.set_y(stamp_y + 15)
        pdf.set_x(17)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*GREY_MID)
        apn12 = re.sub(r"\D", "", apn) if apn else ""
        tax_bill_url = f"https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx?CN=butte&Asmt={apn12}&TaxYear=2025&RollCat=CS&RollType=S&RollYear=" if apn12 else ""
        if doc_numbers and tax_bill_url:
            pdf.cell(0, 4, f"Verify: recorder doc {doc_numbers.split('|')[0]} at recorder.buttecounty.net   |   Tax bill: {tax_bill_url[:90]}...")
        elif tax_bill_url:
            pdf.cell(0, 4, f"View tax bill: {tax_bill_url[:110]}")
        elif doc_numbers:
            pdf.cell(0, 4, f"Verify at recorder.buttecounty.net using doc {doc_numbers.split('|')[0]}   |   Prepared {datetime.now():%B %d, %Y}")
        else:
            pdf.cell(0, 4, f"Prepared {datetime.now():%B %d, %Y} from Butte County public records")

        # Add a real clickable link overlay (fpdf link_url makes the whole cell clickable)
        if tax_bill_url:
            pdf.set_y(stamp_y + 15)
            pdf.set_x(17)
            pdf.link(x=pdf.get_x(), y=pdf.get_y(), w=pdf.w - 34, h=4, link=tax_bill_url)

    # Disclaimer
    pdf.set_y(-16)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*GREY_MID)
    pdf.cell(0, 4, "For information only. Owner status and encumbrances may have changed since preparation. Verify independently before offer or contact.", align="C")

    # ── PAGE 2: TAX BILL DETAIL ──────────────────────────────────────
    # Only render if we have meaningful tax bill data
    if has_tax_bill:
        _build_tax_bill_page(pdf, row, apn, apn12=re.sub(r"\D", "", apn))


def _build_tax_bill_page(pdf: DossierPDF, row: dict, apn: str, apn12: str) -> None:
    """Render page 2: full tax bill detail for the parcel."""
    pdf.add_page()

    owner = _s(row.get("verified_current_owner_name")) or "(no owner)"
    situs = _s(row.get("situs_address")) or "-"
    mailing = _s(row.get("mailing_address")) or "-"

    def _int_or(v, default=0):
        n = pd.to_numeric(v, errors="coerce")
        if pd.isna(n): return default
        try: return int(n)
        except (ValueError, TypeError): return default

    land = _money_to_float(row.get("land_value"))
    improvements = _money_to_float(row.get("improvements_value"))
    net_taxable = _money_to_float(row.get("net_taxable_value"))
    total_billed = _money_to_float(row.get("total_tax_billed"))
    orig_bill_date = _s(row.get("original_bill_date"))
    pts_date = _s(row.get("power_to_sell_date"))
    pts_years = _int_or(row.get("years_since_power_to_sell"), 0)
    redemption_status = _s(row.get("redemption_status"))
    redemption_date = _s(row.get("redemption_date"))
    hox = _s(row.get("homeowner_exemption"))
    installment = _s(row.get("installment_plan_active"))
    special_total = _money_to_float(row.get("special_assessments_total"))
    special_list = _s(row.get("special_assessments_list"))
    important_msgs = _s(row.get("tax_bill_important_messages"))

    # Header band (thinner than page 1)
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, 20, style="F")
    pdf.set_xy(14, 5)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 6, "TAX BILL DETAIL", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"APN {apn}  |  {owner[:60]}")

    pdf.set_y(24)

    # If REDEEMED — big warning at top of page 2 too
    if redemption_status == "redeemed":
        y = pdf.get_y()
        pdf.set_fill_color(*RED)
        pdf.rect(14, y, pdf.w - 28, 8, style="F")
        pdf.set_xy(17, y + 1.5)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, f"REDEEMED {redemption_date} - THIS PARCEL MAY NO LONGER BE ON AUCTION")
        pdf.set_y(y + 12)

    # Property identification
    pdf.set_x(14)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 5, "PROPERTY IDENTIFICATION", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*NAVY); pdf.line(14, pdf.get_y(), 40, pdf.get_y()); pdf.ln(2)
    col_w = pdf.w - 28
    pdf._kv_multi("Assessment number", apn, key_w=50, col_x=14, col_w=col_w)
    pdf._kv_multi("Situs address", situs, key_w=50, col_x=14, col_w=col_w)
    pdf._kv_multi("Mailing address", mailing, key_w=50, col_x=14, col_w=col_w)
    pdf.ln(2)

    # Assessed values
    pdf.set_x(14)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 5, "ASSESSED VALUES  (2026-2027 tax year)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*NAVY); pdf.line(14, pdf.get_y(), 40, pdf.get_y()); pdf.ln(2)

    # Two columns for value breakdown
    y_val = pdf.get_y()
    tb_col2_x = 14 + col_w // 2 + 3
    tb_col_w  = col_w // 2 - 3

    pdf.set_xy(14, y_val)
    pdf._kv("Land value", _fmt_money(land) if land else "-", key_w=40, col_x=14, col_w=tb_col_w)
    pdf._kv("Structural improvements", _fmt_money(improvements) if improvements else "-", key_w=40, col_x=14, col_w=tb_col_w)
    left_end = pdf.get_y()

    pdf.set_xy(tb_col2_x, y_val)
    pdf._kv("Net taxable value", _fmt_money(net_taxable) if net_taxable else "-", key_w=40, col_x=tb_col2_x, col_w=tb_col_w)
    pdf._kv("Total tax billed", _fmt_money(total_billed) if total_billed else "-", key_w=40, col_x=tb_col2_x, col_w=tb_col_w)
    right_end = pdf.get_y()

    pdf.set_y(max(left_end, right_end) + 2)

    # Value ratio hint (vacant land vs improved)
    if land is not None and improvements is not None:
        pdf.set_x(14)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*GREY_MID)
        if improvements == 0 or (land > 0 and improvements / max(land, 1) < 0.05):
            hint = "  Note: >95% land value - likely vacant land / minimal structures"
        elif improvements > land:
            hint = "  Note: improvements exceed land value - substantial building"
        else:
            hint = f"  Improvement-to-land ratio: {(improvements/max(land,1)*100):.0f}%"
        pdf.cell(0, 4, hint, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # Delinquency & Status
    pdf.set_x(14)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 5, "DELINQUENCY STATUS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*NAVY); pdf.line(14, pdf.get_y(), 40, pdf.get_y()); pdf.ln(2)

    if redemption_status == "redeemed":
        status_display = f"REDEEMED on {redemption_date} - delinquency cleared"
        pdf._kv("Current status", status_display, key_w=50, col_x=14, col_w=col_w)
    elif redemption_status == "still_delinquent":
        pdf._kv("Current status", "Still delinquent (no redemption on file)", key_w=50, col_x=14, col_w=col_w)
    else:
        pdf._kv("Current status", "See tax collector for latest status", key_w=50, col_x=14, col_w=col_w)

    pdf._kv("Original bill date", orig_bill_date or "-", key_w=50, col_x=14, col_w=col_w)
    if pts_date:
        pts_display = f"{pts_date}  ({pts_years} years on the roll)"
        pdf._kv("Power to Sell (auction eligible)", pts_display, key_w=50, col_x=14, col_w=col_w)
    pdf._kv("Installment plan",
            "YES - owner is paying down balance" if installment == "Y" else "no",
            key_w=64, col_x=14, col_w=col_w)
    pdf._kv("Homeowner exemption",
            "YES - owner-occupied" if hox == "Y" else "no (rental / absentee / vacant)",
            key_w=64, col_x=14, col_w=col_w)
    pdf.ln(2)

    # Special assessments — full list, not just total
    if special_list:
        pdf.set_x(14)
        pdf.set_text_color(*NAVY)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 5, "SPECIAL ASSESSMENTS & DIRECT CHARGES  (additional annual cost)",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(*NAVY); pdf.line(14, pdf.get_y(), 40, pdf.get_y()); pdf.ln(2)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GREY_DARK)
        # Each assessment on its own line
        for item in special_list.split("|"):
            item = item.strip()
            if item:
                pdf.set_x(18)
                pdf.cell(0, 4.5, "* " + item, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(14)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 5, f"  Total annual special assessments: {_fmt_money(special_total)}",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    # Important messages (verbatim from the bill)
    if important_msgs:
        pdf.set_x(14)
        pdf.set_text_color(*NAVY)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 5, "IMPORTANT MESSAGES  (verbatim from county tax bill)",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(*NAVY); pdf.line(14, pdf.get_y(), 40, pdf.get_y()); pdf.ln(2)

        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*GREY_DARK)
        for msg in important_msgs.split("|"):
            msg = msg.strip()
            if msg:
                pdf.set_x(18)
                pdf.multi_cell(pdf.w - 36, 4.5, "* " + msg)
        pdf.ln(2)

    # Source footer — disable auto page break while drawing so cell() advances
    # don't spill into a new page. Re-enable after.
    src_url = f"https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx?CN=butte&Asmt={apn12}&TaxYear=2025&RollCat=CS&RollType=S&RollYear="
    pdf.set_auto_page_break(auto=False)
    try:
        footer_y = pdf.h - 22
        pdf.set_fill_color(*BG_LIGHT)
        pdf.rect(14, footer_y, pdf.w - 28, 14, style="F")
        pdf.set_xy(17, footer_y + 1.5)
        pdf.set_text_color(*NAVY)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 4, "SOURCE", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(17)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*GREY_DARK)
        pdf.cell(0, 4, "Butte County Treasurer-Tax Collector - Secured Tax Roll FY 2026-2027",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(17)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*NAVY_LIGHT)
        pdf.cell(0, 4, f"Click here to view live tax bill at Butte TTC   |   Archived: tax_bills/{apn12}.html")
        pdf.link(x=14, y=footer_y, w=pdf.w - 28, h=14, link=src_url)

        # Disclaimer (small, at very bottom)
        pdf.set_xy(14, pdf.h - 6)
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(*GREY_MID)
        pdf.cell(pdf.w - 28, 4,
                 "Values reflect the last-published tax bill; verify current status via county URL above.",
                 align="C")
    finally:
        pdf.set_auto_page_break(auto=True, margin=12)


def build_all(csv_path: str, output_dir: str, combined_path: str | None = None,
              limit: int | None = None) -> dict:
    """Generate one dossier per row + optionally a combined PDF."""
    df = pd.read_csv(csv_path, dtype=str)
    df["_priority"] = pd.to_numeric(df["priority_score"], errors="coerce").fillna(0)
    df = df.sort_values("_priority", ascending=False).reset_index(drop=True)

    if limit:
        df = df.head(limit)

    os.makedirs(output_dir, exist_ok=True)

    total = len(df)
    combined_pdf = DossierPDF() if combined_path else None
    written = []

    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        apn = _s(row.get("apn")) or f"UNKNOWN_{rank}"
        owner_slug = _sanitize_filename(_s(row.get("verified_current_owner_name")) or "NO_OWNER", 30)
        score = float(row.get("_priority") or 0)
        fname = f"{rank:03d}_score{score:04.1f}_{apn}_{owner_slug}.pdf"
        fpath = os.path.join(output_dir, fname)

        # Per-parcel PDF
        p = DossierPDF()
        build_dossier(p, row.to_dict(), rank=rank, total=total)
        p.output(fpath)
        written.append(fpath)

        # Add to combined
        if combined_pdf is not None:
            build_dossier(combined_pdf, row.to_dict(), rank=rank, total=total)

    if combined_pdf is not None and combined_path:
        combined_pdf.output(combined_path)

    return {
        "count": len(written),
        "output_dir": output_dir,
        "combined_path": combined_path,
        "files": written,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"))
    p.add_argument("--outdir", default=None, help="Defaults to delivery/butte_auction_YYYY-MM-DD/dossiers")
    p.add_argument("--combined", default=None, help="Path for combined all-dossiers PDF")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    if not args.outdir:
        date_slug = datetime.now().strftime("%Y-%m-%d")
        args.outdir = os.path.join(os.path.dirname(__file__), "delivery", f"butte_auction_{date_slug}", "dossiers")
    if not args.combined:
        args.combined = os.path.join(os.path.dirname(args.outdir), "butte_auction_all_dossiers.pdf")

    result = build_all(args.csv, args.outdir, args.combined, args.limit)
    print(f"Wrote {result['count']} dossiers to {result['output_dir']}")
    if result['combined_path']:
        size = os.path.getsize(result['combined_path'])
        print(f"Combined PDF: {result['combined_path']} ({size:,} bytes)")
