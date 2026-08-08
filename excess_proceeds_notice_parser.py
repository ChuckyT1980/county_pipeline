"""
Reusable, configurable parser for CA county "Notice of Right to Claim
Excess Proceeds" / "Parties of Interest" PDFs.

These notices vary by county in real, structural ways already observed
tonight:
  - Humboldt/Tulare/San Joaquin: one global sale date, amounts published
    per parcel (San Joaquin/Tulare also have owner names in the same doc).
  - Shasta/Colusa: parties of interest (real names) published, but NO
    dollar amounts - county discloses the amount only after a claim is
    filed. Colusa additionally publishes a DIFFERENT deadline PER PARCEL
    (not one global deadline like Shasta/Humboldt).

Rather than one hardcoded script per county (the pattern used earlier
tonight for Humboldt/Shasta/Tulare/Sonoma/Madera/San Joaquin), this
module takes a per-county CONFIG describing the notice's real structure,
and applies one general parsing routine. Add a new county by writing a
config, not a new script.

USAGE:
    from excess_proceeds_notice_parser import parse_parties_of_interest_notice, COLUSA_CONFIG
    records = parse_parties_of_interest_notice(pdf_text, COLUSA_CONFIG)

FIELD MAPPING (what every record dict contains):
    apn                 - str, dash-formatted APN as printed in the source
    situs               - str or None (many parcels have no situs printed)
    parties_of_interest - list[str], ALL parties as printed (institutional
                           and private both included - filtering is a
                           separate step, see filter_institutional())
    deadline            - str (YYYY-MM-DD) or None, PER-PARCEL if the
                           config says per_parcel_deadline=True, else the
                           notice's single global deadline
    amount              - float or None (None means "not disclosed by
                           this county" - NEVER treat as $0)

KNOWN EXCEPTIONS / LIMITATIONS (document honestly, don't paper over):
  - A parcel block with an unparseable deadline is returned with
    deadline=None and flagged in `parse_failures` - it is NOT dropped
    silently, and it is NOT assigned the notice's global date as a guess.
  - Institutional-vs-private classification is a keyword heuristic
    (INSTITUTIONAL_MARKERS below) - it can misclassify an ambiguously-named
    real entity (e.g. a family trust with an unusual name). Always spot-
    check before treating the "private" list as final for outreach.
  - This parser does not attempt to extract dollar amounts - counties that
    publish amounts alongside owner names (Humboldt, Tulare, San Joaquin,
    Madera) have a genuinely different document structure (a straight
    table, not a "parties of interest" block-per-parcel format) and are
    better served by a simple table-row regex, not this module.
  - CONFIRMED REAL LIMITATION (found testing against Colusa 2026-08-08):
    when a situs address is followed by ", <CITY NAME>" before the first
    party name on the same squished PDF-extraction line, the address
    regex stops at the street-type suffix (ST/AVE/etc.) and the city name
    + first party name end up concatenated in parties_of_interest (e.g.
    "522 WATERFOWL WAY" correctly split as situs, but the next field came
    through as ", WILLIAMS  AMBER MENDEZ KESTERSON" instead of cleanly
    separating city "WILLIAMS" from party "AMBER MENDEZ KESTERSON").
    Similarly, an OCR/extraction artifact splitting "AVE" into "A VE"
    (real, observed on one Colusa record) breaks the street-suffix match
    entirely and the whole address+name string falls through into
    parties_of_interest unsplit. NEITHER case drops data - the full
    original text is preserved in the parties_of_interest list either
    way - but automatic situs/name separation is not reliable enough to
    trust unreviewed for outreach-grade output. Hand-verify against the
    original extracted text before publishing when a record contains a
    comma or an unusual multi-word street suffix.
"""
import re
from dataclasses import dataclass, field


@dataclass
class NoticeConfig:
    county: str
    source_url: str
    source_note: str
    per_parcel_deadline: bool
    # Regex for one parcel "block": must capture apn, and either a single
    # trailing deadline (per_parcel_deadline=True) or nothing (deadline
    # comes from global_deadline_pattern instead).
    apn_pattern: str = r"(\d{3}-\d{3}-\d{3}(?:-\d{3})?)"
    deadline_pattern: str = r"([A-Z]+ \d{1,2},? \d{4})"
    global_deadline_pattern: str | None = None  # used when per_parcel_deadline=False


INSTITUTIONAL_MARKERS = [
    "COUNTY OF", "STATE OF CALIFORNIA", "FRANCHISE TAX BOARD", "INTERNAL REVENUE SERVICE",
    "TAX COLLECTOR", "TITLE INSURANCE", "SURETY", "RESOURCE MGMT", "RESOURCE MNGT",
    "RESOURCE MANAGEMENT", "DEPT OF", "CITY OF", "FINANCE AUTHORITY", "RECOVERY ASSOCIATES",
    "PORTFOLIO RECOVERY",
]


def _parse_date_to_iso(raw: str) -> str | None:
    """'OCTOBER 6, 2026' -> '2026-10-06'. Returns None if unparseable."""
    months = {
        "JANUARY": "01", "FEBRUARY": "02", "MARCH": "03", "APRIL": "04",
        "MAY": "05", "JUNE": "06", "JULY": "07", "AUGUST": "08",
        "SEPTEMBER": "09", "OCTOBER": "10", "NOVEMBER": "11", "DECEMBER": "12",
    }
    m = re.match(r"([A-Z]+)\s+(\d{1,2}),?\s+(\d{4})", raw.strip().upper())
    if not m:
        return None
    month_name, day, year = m.groups()
    month = months.get(month_name)
    if not month:
        return None
    return f"{year}-{month}-{int(day):02d}"


def parse_parties_of_interest_notice(text: str, config: NoticeConfig) -> dict:
    """
    Returns {"records": [...], "parse_failures": [...]}.
    Never guesses a missing deadline or amount - missing means None,
    logged in parse_failures if a value was expected but not found.
    """
    records = []
    parse_failures = []

    # Cut off the document's footer/signature section before block-splitting,
    # so the last parcel's block doesn't bleed into "Claim forms...",
    # "I certify...", the signature name, etc. Real bug found via direct
    # testing on Colusa - the last APN's block ran to end-of-text otherwise.
    footer_m = re.search(r"Claim forms and information", text)
    body_text = text[:footer_m.start()] if footer_m else text

    apn_re = re.compile(config.apn_pattern)
    matches = list(apn_re.finditer(body_text))

    for i, m in enumerate(matches):
        apn = m.group(1)
        block_start = m.end()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(body_text)
        block = body_text[block_start:block_end]

        deadline_iso = None
        first_line_remainder = ""
        if config.per_parcel_deadline:
            dm = re.search(config.deadline_pattern, block)
            if dm:
                deadline_iso = _parse_date_to_iso(dm.group(1))
                # Real PDF-extraction quirk (confirmed on Colusa): the
                # deadline, situs, and first party name are often on ONE
                # squished line with no separator (column boundaries are
                # lost in text extraction). Capture whatever follows the
                # deadline on that same line separately from later lines.
                first_line_remainder = block[dm.end():].split("\n", 1)[0].strip()
                block = block[dm.end():]  # continue parsing after the deadline
                if "\n" in block:
                    block = block.split("\n", 1)[1]  # drop the (already-captured) first line
                else:
                    block = ""
            if not deadline_iso:
                parse_failures.append({
                    "apn": apn, "issue": "no per-parcel deadline found/parsed in this block",
                    "raw_block": block[:200],
                })
        elif config.global_deadline_pattern:
            gm = re.search(config.global_deadline_pattern, text)
            if gm:
                deadline_iso = _parse_date_to_iso(gm.group(1))

        # Situs may be embedded in first_line_remainder (address + name
        # squished together) - split it out if an address pattern matches
        # at the start, whatever's left on that line is the first party.
        situs = None
        first_party_from_line1 = None
        addr_m = re.match(r"(\d+[^\n]{3,70}?(?:ST|AVE|WAY|RD|DR|CT|LN|BLVD|PL)(?:[.,]?\s*#?\w*)?)\s+(.*)$",
                           first_line_remainder)
        if addr_m:
            situs = addr_m.group(1).strip()
            first_party_from_line1 = addr_m.group(2).strip() or None
        elif first_line_remainder:
            first_party_from_line1 = first_line_remainder.strip() or None

        parties = []
        if first_party_from_line1:
            parties.append(first_party_from_line1)
        for line in block.split("\n"):
            line = line.strip()
            if not line or len(line) < 3:
                continue
            parties.append(line)

        if not parties:
            parse_failures.append({"apn": apn, "issue": "no parties of interest parsed in this block",
                                    "raw_block": (first_line_remainder + " | " + block)[:200]})

        records.append({
            "apn": apn,
            "situs": situs,
            "parties_of_interest": parties,
            "deadline": deadline_iso,
            "amount": None,  # this notice type never publishes amounts
        })

    return {"records": records, "parse_failures": parse_failures}


def filter_institutional(parties: list[str]) -> tuple[list[str], list[str]]:
    """Returns (private_parties, institutional_parties)."""
    private, institutional = [], []
    for p in parties:
        up = p.upper()
        if any(marker in up for marker in INSTITUTIONAL_MARKERS):
            institutional.append(p)
        else:
            private.append(p)
    return private, institutional


# ── Per-county configs ───────────────────────────────────────────────────
COLUSA_CONFIG = NoticeConfig(
    county="colusa",
    source_url="https://www.countyofcolusaca.gov/DocumentCenter/View/19919/25-Parties-of-interest-publication",
    source_note=(
        "Colusa County official 'Notice of Right to Claim Excess Proceeds "
        "(Parties of Interest)', executed 2025-12-15, published Pioneer Review "
        "12/26/2025, 1/2/2026, 1/9/2026. Covers sales on 2025-09-18 and 2025-11-05."
    ),
    per_parcel_deadline=True,  # Colusa is unusual: each parcel has its OWN "LAST DAY TO FILE"
    apn_pattern=r"(\d{3}-\d{3}-\d{3}(?:-\d{3})?)",
    deadline_pattern=r"([A-Z]+ \d{1,2}, \d{4})",
)

SHASTA_CONFIG = NoticeConfig(
    county="shasta",
    source_url="https://www.shastacounty.gov/media/81921",
    source_note="Shasta County official notice, single global deadline for all parcels.",
    per_parcel_deadline=False,
    global_deadline_pattern=r"DEADLINE:\s*([A-Z]+ \d{1,2}, \d{4})",
)
