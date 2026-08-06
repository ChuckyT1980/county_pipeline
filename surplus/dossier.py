"""
Surplus recovery dossier generator.

For each open surplus_opportunity, generate a 1-page branded PDF a lead
agent can work: former owner name + surplus amount + prominent countdown
to claim deadline + skip-trace results (when available) + county-specific
claim-filing instructions.

Reuses the branded PDF style from butte/build_dossiers.py.
"""
import argparse
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .db import connect


# Brand palette (matches butte/build_dossiers)
NAVY       = (31, 58, 95)
NAVY_LIGHT = (46, 134, 171)
GREY_DARK  = (60, 60, 60)
GREY_MID   = (120, 120, 120)
BG_LIGHT   = (232, 241, 247)
BG_HIGH    = (255, 232, 200)
BG_URGENT  = (255, 210, 180)
RED        = (192, 60, 60)
GREEN      = (60, 140, 80)
ORANGE     = (210, 130, 40)
WHITE      = (255, 255, 255)

_NON_LATIN1 = {
    "–": "-", "—": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "•": "*",
    "�": "?", "\xa0": " ",
}


def _l1(text):
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    for bad, good in _NON_LATIN1.items():
        if bad in text:
            text = text.replace(bad, good)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _fmt_money(v):
    if v is None:
        return "-"
    return f"${v:,.0f}"


def _days_until(iso_date: str) -> int | None:
    if not iso_date:
        return None
    try:
        d = date.fromisoformat(iso_date[:10])
        return (d - date.today()).days
    except (ValueError, TypeError):
        return None


def _urgency_color(days_left: int | None) -> tuple:
    if days_left is None:
        return GREY_MID
    if days_left < 0:
        return RED         # expired
    if days_left < 60:
        return RED         # urgent
    if days_left < 180:
        return ORANGE
    return GREEN


def _sanitize_filename(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\s-]", "", text or "").strip()
    s = re.sub(r"\s+", "_", s)
    return s[:max_len] or "UNKNOWN"


class SurplusDossier(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.set_auto_page_break(auto=True, margin=12)
        self.set_margins(left=14, top=12, right=14)

    def cell(self, w=None, h=None, text="", *args, **kwargs):
        return super().cell(w, h, _l1(text), *args, **kwargs)

    def multi_cell(self, w, h=None, text="", *args, **kwargs):
        return super().multi_cell(w, h, _l1(text), *args, **kwargs)


def build_dossier(pdf: SurplusDossier, opp: dict, trace: dict | None = None,
                   rank: int = 0, total: int = 0) -> None:
    """Render one surplus opportunity to a fresh page."""
    pdf.add_page()

    apn = opp.get("apn") or ""
    county = (opp.get("county") or "").upper()
    former_owner = opp.get("former_owner_raw") or "(name not on list)"
    surplus = opp.get("surplus_amount")
    deed_date = opp.get("deed_date") or ""
    deadline = opp.get("claim_deadline_at") or ""
    days_left = _days_until(deadline)
    urgency = _urgency_color(days_left)

    # ── Header band ──────────────────────────────────────────────────
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, 32, style="F")

    # Surplus amount badge (top-left)
    pdf.set_fill_color(*urgency)
    pdf.rect(14, 6, 44, 20, style="F")
    pdf.set_xy(14, 6)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(44, 4, "SURPLUS OWED", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(44, 11, _fmt_money(surplus), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 6.5)
    if days_left is not None:
        if days_left < 0:
            pdf.cell(44, 3, f"expired {abs(days_left)} days ago", align="C")
        elif days_left < 30:
            pdf.cell(44, 3, f"URGENT: {days_left} days left", align="C")
        else:
            pdf.cell(44, 3, f"{days_left} days to claim", align="C")

    # Header text
    pdf.set_xy(62, 8)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 6, former_owner[:60], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(62)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"{county} County  |  APN {apn}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(62)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(220, 230, 240)
    if rank and total:
        pdf.cell(0, 4, f"Surplus recovery opportunity  |  rank {rank} of {total}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 4, "Tax sale surplus recovery opportunity", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_y(36)

    # ── Deadline banner ───────────────────────────────────────────────
    if days_left is not None and days_left >= 0 and days_left < 90:
        pdf.set_fill_color(*BG_URGENT)
        pdf.rect(14, 36, pdf.w - 28, 8, style="F")
        pdf.set_xy(17, 37.5)
        pdf.set_text_color(*RED)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, f"CLAIM DEADLINE: {deadline}  ({days_left} days remaining)  -  {county} County TTC")
        pdf.set_y(46)

    # ── Two-column body ───────────────────────────────────────────────
    body_y = pdf.get_y()
    col_w = (pdf.w - 28 - 6) / 2
    col1_x = 14
    col2_x = 14 + col_w + 6

    # LEFT: CLAIM DETAILS
    pdf.set_xy(col1_x, body_y)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 5, "CLAIM DETAILS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*NAVY)
    pdf.line(col1_x, pdf.get_y(), col1_x + 25, pdf.get_y())
    pdf.ln(2)

    _kv(pdf, "Parcel APN",         apn,                col1_x, col_w)
    _kv(pdf, "Former owner",       former_owner,       col1_x, col_w)
    _kv(pdf, "County",             county.title() + " County (CA)", col1_x, col_w)
    _kv(pdf, "Sale price",         _fmt_money(opp.get("sale_price")), col1_x, col_w)
    _kv(pdf, "Taxes + fees paid",  _fmt_money(_money_from_opp(opp, "sale_price", "surplus_amount")), col1_x, col_w)
    _kv(pdf, "Surplus owed",       _fmt_money(surplus), col1_x, col_w)
    _kv(pdf, "Deed recorded",      deed_date,          col1_x, col_w)
    _kv(pdf, "Claim deadline",     deadline,           col1_x, col_w)

    left_end = pdf.get_y()

    # RIGHT: OWNER CONTACT (skip-trace results)
    pdf.set_xy(col2_x, body_y)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 5, "OWNER CONTACT", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*NAVY)
    pdf.line(col2_x, pdf.get_y(), col2_x + 25, pdf.get_y())
    pdf.ln(2)

    if trace:
        current_addr = trace.get("current_address") or ""
        current_cs = trace.get("current_city_state") or ""
        phones = json.loads(trace.get("phones_json") or "[]")
        emails = json.loads(trace.get("emails_json") or "[]")
        is_deceased = bool(trace.get("is_deceased"))
        provider = trace.get("provider") or "?"

        if is_deceased:
            _kv(pdf, "STATUS", "DECEASED - heir search needed", col2_x, col_w)
            if trace.get("date_of_death"):
                _kv(pdf, "Date of death", trace["date_of_death"], col2_x, col_w)
            relatives = json.loads(trace.get("relatives_json") or "[]")
            if relatives:
                names = [r.get("name","") for r in relatives if r.get("name")][:3]
                _kv(pdf, "Known relatives", ", ".join(names), col2_x, col_w)
        else:
            if current_addr:
                _kv_multi(pdf, "Current address", f"{current_addr} {current_cs}".strip(), col2_x, col_w)
            for i, ph in enumerate(phones[:3]):
                _kv(pdf, f"Phone {i+1}" if i > 0 else "Phone", ph.get("number", ""), col2_x, col_w)
            for i, em in enumerate(emails[:2]):
                _kv(pdf, "Email" if i == 0 else f"Email {i+1}", em, col2_x, col_w)
            if trace.get("age"):
                _kv(pdf, "Age", str(trace["age"]), col2_x, col_w)
        _kv(pdf, "Source", provider, col2_x, col_w)
    else:
        pdf.set_x(col2_x)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*GREY_MID)
        pdf.multi_cell(col_w, 4.5, "Not yet skip-traced. Run:\n  python -m surplus.trace --county " + opp.get("county",""))

    # Last-known address (from county list, which is the mailing-of-record when they lost the property)
    pdf.ln(1)
    pdf.set_x(col2_x)
    pdf.set_text_color(*GREY_MID)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 4, "Last-known address (per county):", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(col2_x)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GREY_DARK)
    lka = opp.get("last_known_address") or opp.get("mailing_address") or "(not in county excess proceeds list)"
    pdf.multi_cell(col_w, 4, lka)

    right_end = pdf.get_y()

    pdf.set_y(max(left_end, right_end) + 4)

    # ── Filing instructions ──────────────────────────────────────────
    pdf.set_fill_color(*BG_LIGHT)
    y0 = pdf.get_y()
    pdf.rect(14, y0, pdf.w - 28, 32, style="F")
    pdf.set_xy(17, y0 + 1.5)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, "TO FILE THIS CLAIM", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(17)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY_DARK)
    pdf.multi_cell(pdf.w - 34, 4.4,
        f"1) Secure signed contingency agreement from former owner (or their heirs if deceased).\n"
        f"2) File the county's Claim for Excess Proceeds form with {county.title()} County Treasurer-Tax Collector, referencing APN {apn} and the deed date {deed_date}.\n"
        f"3) Deadline: {deadline} - AFTER THIS DATE THE CLAIM IS DEAD. Do not miss it.\n"
        f"4) Claim processed per county schedule; payment disbursed at that time.")

    # Footer
    pdf.set_y(-16)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*GREY_MID)
    pdf.cell(0, 4,
        f"Source: {opp.get('source_url','(county TTC list)')[:110]}   "
        f"Ingested: {(opp.get('ingested_at') or '')[:10]}",
        align="C")


def _kv(pdf: SurplusDossier, key: str, value: str,
         col_x: float, col_w: float, key_w: float = 34, size: int = 9):
    pdf.set_x(col_x)
    pdf.set_font("Helvetica", "B", size)
    pdf.set_text_color(*GREY_MID)
    pdf.cell(key_w, 4.5, key)
    pdf.set_font("Helvetica", "", size)
    pdf.set_text_color(*GREY_DARK)
    pdf.cell(col_w - key_w, 4.5, value or "-", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(col_x)


def _kv_multi(pdf: SurplusDossier, key: str, value: str,
               col_x: float, col_w: float, key_w: float = 34, size: int = 9):
    pdf.set_x(col_x)
    pdf.set_font("Helvetica", "B", size)
    pdf.set_text_color(*GREY_MID)
    pdf.cell(key_w, 4.5, key)
    pdf.set_font("Helvetica", "", size)
    pdf.set_text_color(*GREY_DARK)
    pdf.set_x(col_x + key_w)
    pdf.multi_cell(col_w - key_w, 4.5, value or "-")
    pdf.set_x(col_x)


def _money_from_opp(opp, minus_from, minus_by):
    """Compute (sale_price - surplus) as an estimate of taxes+fees paid."""
    sp = opp.get(minus_from)
    su = opp.get(minus_by)
    if sp is None or su is None:
        return None
    try:
        return float(sp) - float(su)
    except (ValueError, TypeError):
        return None


def _load_trace(conn, canonical_name: str) -> dict | None:
    if not canonical_name:
        return None
    r = conn.execute(
        """SELECT * FROM skip_trace_results
             WHERE canonical_name = ?
             ORDER BY request_at DESC LIMIT 1""",
        (canonical_name,),
    ).fetchone()
    return dict(r) if r else None


def build_all(output_dir: str, combined_path: str | None = None,
              include_expired: bool = False,
              min_surplus: float = 1000.0) -> dict:
    """Generate one dossier per open surplus opportunity above the threshold."""
    conn = connect()
    today = date.today().isoformat()

    where = "surplus_amount >= ?"
    params: list = [min_surplus]
    if not include_expired:
        where += " AND (claim_deadline_at IS NULL OR claim_deadline_at > ?)"
        params.append(today)

    rows = conn.execute(
        f"SELECT * FROM surplus_opportunities WHERE {where} ORDER BY surplus_amount DESC",
        params,
    ).fetchall()

    os.makedirs(output_dir, exist_ok=True)
    total = len(rows)
    combined_pdf = SurplusDossier() if combined_path else None
    written = []

    for rank, r in enumerate(rows, start=1):
        opp = dict(r)
        trace = _load_trace(conn, opp.get("former_owner_canonical") or "")

        owner_slug = _sanitize_filename(opp.get("former_owner_raw") or "NO_OWNER", 30)
        apn = opp.get("apn") or f"UNKNOWN_{rank}"
        surplus = int(opp.get("surplus_amount") or 0)
        fname = f"{rank:03d}_surplus{surplus:07d}_{opp.get('county','xx')}_{apn}_{owner_slug}.pdf"
        fpath = os.path.join(output_dir, fname)

        p = SurplusDossier()
        build_dossier(p, opp, trace=trace, rank=rank, total=total)
        p.output(fpath)
        written.append(fpath)

        if combined_pdf is not None:
            build_dossier(combined_pdf, opp, trace=trace, rank=rank, total=total)

    if combined_pdf is not None and combined_path:
        combined_pdf.output(combined_path)

    conn.close()
    return {"count": len(written), "output_dir": output_dir, "combined_path": combined_path}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--outdir", default=None)
    p.add_argument("--combined", default=None)
    p.add_argument("--include-expired", action="store_true")
    p.add_argument("--min-surplus", type=float, default=1000.0)
    args = p.parse_args()

    if not args.outdir:
        args.outdir = str(Path(__file__).resolve().parent / "delivery" / f"surplus_{date.today().isoformat()}")
    if not args.combined:
        args.combined = os.path.join(os.path.dirname(args.outdir), f"surplus_all_dossiers_{date.today().isoformat()}.pdf")

    r = build_all(args.outdir, args.combined,
                   include_expired=args.include_expired,
                   min_surplus=args.min_surplus)
    print(f"Wrote {r['count']} dossiers to {r['output_dir']}")
    if r['combined_path']:
        print(f"Combined: {r['combined_path']}")
