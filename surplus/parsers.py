"""
Parsers for county excess proceeds lists.

Each parser is a function that takes a raw file (PDF bytes or HTML text)
and returns a list of dicts, each dict representing one surplus opportunity
with fields the ingester knows how to save.

Registered via PARSERS at the bottom; referenced by CountySource.parser_key.

Row output shape:
    {
        "apn": "010-383-002-000",
        "former_owner_raw": "Pritchett Barbara J",
        "sale_price": 16000.00,        # winning bid
        "taxes_and_fees": 2061.51,
        "surplus_amount": 13938.49,
        "deed_date": "2024-02-22",     # ISO
        "sale_date": None,             # sometimes distinct from deed_date
    }
"""
import re
from datetime import datetime, timedelta
from io import BytesIO

import pdfplumber


MONEY_RE = re.compile(r"\$?[\d,]+\.\d{2}")
DATE_RE  = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})")
APN_RE   = re.compile(r"\b(\d{3}-\d{3}-\d{3}(?:-\d{3})?)\b")


def _to_float(s):
    if not s:
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _to_iso(datestr):
    """Convert 'M/D/YYYY' or similar to ISO 'YYYY-MM-DD'."""
    if not datestr:
        return None
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(datestr.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def add_year(iso_date: str) -> str | None:
    """Return iso_date + 1 year for claim deadline calc."""
    if not iso_date:
        return None
    try:
        d = datetime.fromisoformat(iso_date)
        return (d + timedelta(days=365)).date().isoformat()
    except (ValueError, TypeError):
        return None


# ── Mono County parser ─────────────────────────────────────────────────
# Format seen in Feb 2024 PDF: single-page, table with 6 columns
#   APN | Assessee Name | Date Deeded | Winning Bid | Total Taxes & Fees Paid | Est. Excess Proceeds

def parse_mono(pdf_bytes: bytes) -> list[dict]:
    out = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        full_text = ""
        for p in pdf.pages:
            full_text += (p.extract_text() or "") + "\n"

    # Line-based parse: each qualifying line starts with an APN
    for line in full_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = APN_RE.search(line)
        if not m:
            continue
        apn = m.group(1)
        # Find dates + money amounts on the line
        dates = DATE_RE.findall(line)
        money = MONEY_RE.findall(line)
        if len(money) < 3:
            continue                # need at least: winning bid, taxes, surplus
        # After the APN there should be: name text, date, then 3 money amounts
        after_apn = line[m.end():].strip()
        # Strip the trailing dates + money to get the name
        clean_name = after_apn
        for d in dates:
            clean_name = clean_name.replace(d, "")
        for mm in money:
            clean_name = clean_name.replace(mm, "")
        clean_name = re.sub(r"\s+", " ", clean_name).strip(" ,")

        deed_date = _to_iso(dates[0]) if dates else None
        winning_bid = _to_float(money[0])
        taxes_fees  = _to_float(money[1])
        surplus     = _to_float(money[2])

        out.append({
            "apn": apn,
            "former_owner_raw": clean_name,
            "sale_price": winning_bid,
            "taxes_and_fees": taxes_fees,
            "surplus_amount": surplus,
            "deed_date": deed_date,
            "sale_date": deed_date,     # Mono lists date deeded, treats as sale date proxy
        })
    return out


# ── Generic PDF parser ─────────────────────────────────────────────────
# Fallback for counties whose lists have similar shape to Mono but slightly
# different column ordering. Uses same "APN + dates + 3 money amounts" heuristic.
# Note: this is intentionally conservative — better to skip a row than
# ingest garbage. Every unparsed row gets logged so parser can be tuned.

def parse_generic_pdf(pdf_bytes: bytes) -> list[dict]:
    """Same as Mono for now — the shape appears standard across counties.
    County-specific parsers should be added as needed when this heuristic
    fails on a particular county's format."""
    return parse_mono(pdf_bytes)


# ── Registry ───────────────────────────────────────────────────────────

PARSERS = {
    "mono":         parse_mono,
    "generic_pdf":  parse_generic_pdf,
}


def get_parser(key: str):
    return PARSERS.get(key, parse_generic_pdf)
