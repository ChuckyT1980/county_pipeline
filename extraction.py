"""
LAYER A: Extraction — dumb raw parser.
Converts messy text into raw field dicts. No decisions. No scoring. No tiers.
"""
import re

APN_LOOSE = re.compile(r"\d{3}[- ]?\d{3}[- ]?\d{3}[- ]?\d{0,4}")
MONEY     = re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")


def extract_records(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    records = []
    for idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        apn_match = APN_LOOSE.search(line)
        amt_match = MONEY.search(line)

        records.append({
            "line_id":    idx,
            "raw":        line,
            "apn":        apn_match.group(0) if apn_match else None,
            "owner_raw":  _owner_slice(line, apn_match, amt_match),
            "address_raw": _address_slice(line, amt_match),
            "amount_raw": amt_match.group(0) if amt_match else None,
        })

    return records


def _owner_slice(line, apn_match, amt_match):
    """Capture text between APN end and first $ sign."""
    start = apn_match.end() if apn_match else 0
    end   = amt_match.start() if amt_match else len(line)
    return line[start:end].strip(" .,")


def _address_slice(line, amt_match):
    """Capture text after the first $ sign."""
    if not amt_match:
        return ""
    return line[amt_match.end():].strip(" .,")
