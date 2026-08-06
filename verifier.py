#!/usr/bin/env python3
"""
Property Intelligence Verification Pipeline
Tehama County - MBC Portal Verifier
Version 1.0
"""

import csv
import json
import time
import requests
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TAX_YEAR = "2025"
REQUEST_DELAY = 1.5  # seconds between requests — be polite
TIMEOUT = 15

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

COUNTY_CONFIG = {
    "tehama":   {"host": "common1.mptsweb.com", "slug": "tehama"},
    "eldorado": {"host": "common3.mptsweb.com", "slug": "eldorado"},
    "tulare":   {"host": "common2.mptsweb.com", "slug": "tulare"},
    "kings":    {"host": "common1.mptsweb.com", "slug": "kings"},
    "amador":   {"host": "common1.mptsweb.com", "slug": "amador"},
    "mono":     {"host": "common2.mptsweb.com", "slug": "mono"},
}

def get_portal_base(county: str) -> str:
    conf = COUNTY_CONFIG.get(county.lower())
    if not conf:
        raise ValueError(f"County '{county}' not configured for MBC platform.")
    return f"https://{conf['host']}/MBC/{conf['slug']}/tax/main"

# ─────────────────────────────────────────────
# PARCEL NORMALIZER
# ─────────────────────────────────────────────
def normalize_parcel(raw: str) -> str:
    """Strip dashes from parcel number for URL."""
    return re.sub(r"[^0-9]", "", raw.strip())


# ─────────────────────────────────────────────
# PORTAL SCRAPER
# ─────────────────────────────────────────────
def scrape_parcel(parcel_raw: str, county: str) -> dict:
    parcel_clean = normalize_parcel(parcel_raw)
    portal_base = get_portal_base(county)
    url = f"{portal_base}/{parcel_clean}/{TAX_YEAR}/0000"
    result = {
        "portal_url": url,
        "portal_fetch_success": False,
        "portal_http_status": None,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        # Taxes tab
        "current_year_paid_1st": None,
        "current_year_paid_2nd": None,
        "portal_balance_1st": None,
        "portal_balance_2nd": None,
        "portal_total_balance": None,
        "first_delinq_date": None,
        "second_delinq_date": None,
        "first_paid_date": None,
        "second_paid_date": None,
        "first_total_due": None,
        "second_total_due": None,
        # Assessment tab
        "document_number": None,
        "roll_category": None,
        "situs_address": None,
        # Flags
        "prior_defaults": False,
        "has_defaulted_tab": False,
        # Derived
        "portal_status": None,
        "verification_result": None,
        "verification_reason": None,
        "verified_score": None,
        "confidence_pct": None,
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        result["portal_http_status"] = resp.status_code

        if resp.status_code != 200:
            result["portal_status"] = "NOT_FOUND"
            result["verification_result"] = "ERROR"
            result["verification_reason"] = f"HTTP {resp.status_code}"
            return result

        result["portal_fetch_success"] = True
        soup = BeautifulSoup(resp.text, "html.parser")

        # ── Check for PAY DEFAULTED TAXES tab ──
        tabs = soup.find_all("a", class_="nav-link")
        for tab in tabs:
            if "DEFAULTED" in tab.get_text(strip=True).upper():
                result["has_defaulted_tab"] = True
                result["prior_defaults"] = True
                break

        # ── Parse TAXES tab ──
        _parse_taxes_tab(soup, result)

        # ── Parse ASSESSMENT INFO tab (need separate request) ──
        _parse_assessment_tab(parcel_clean, result)
        _extract_assessment_from_soup(soup, result)

        # ── Derive verification result ──
        _derive_result(result)

    except requests.exceptions.Timeout:
        result["verification_result"] = "ERROR"
        result["verification_reason"] = "Request timeout"
    except Exception as e:
        result["verification_result"] = "ERROR"
        result["verification_reason"] = str(e)[:120]

    return result


# ─────────────────────────────────────────────
# TAX TAB PARSER
# ─────────────────────────────────────────────
def _parse_taxes_tab(soup: BeautifulSoup, result: dict):
    """Extract installment data from the TAXES tab."""
    installment_sections = soup.find_all("h3", string=re.compile(r"Installment", re.I))

    for i, section in enumerate(installment_sections[:2]):
        num = i + 1
        parent = section.find_parent("div") or section.find_next_sibling("div")
        if not parent:
            continue

        text_block = parent.get_text(" ", strip=True)

        paid_status = _extract_field(text_block, "Paid Status")
        delinq_date = _extract_field(text_block, "Delinq. Date") or _extract_field(text_block, "Delinquent Date")
        paid_date = _extract_field(text_block, "Paid Date")
        total_due = _extract_field(text_block, "Total Due")
        balance = _extract_field(text_block, "Balance")

        if num == 1:
            result["current_year_paid_1st"] = paid_status
            result["first_delinq_date"] = delinq_date
            result["first_paid_date"] = paid_date
            result["first_total_due"] = total_due
            result["portal_balance_1st"] = balance
        else:
            result["current_year_paid_2nd"] = paid_status
            result["second_delinq_date"] = delinq_date
            result["second_paid_date"] = paid_date
            result["second_total_due"] = total_due
            result["portal_balance_2nd"] = balance

    full_text = soup.get_text(" ", strip=True)
    total_balance = _extract_field(full_text, "Total Balance")
    result["portal_total_balance"] = total_balance


# ─────────────────────────────────────────────
# ASSESSMENT TAB PARSER
# ─────────────────────────────────────────────
def _parse_assessment_tab(parcel_clean: str, result: dict):
    """Fetch and parse the assessment info tab for document number, deed info."""
    try:
        cfg = get_county_config(result.get("county", "tehama"))
        host = cfg["host"]
        slug = cfg["slug"]
        url = f"https://{host}/MBC/{slug}/tax/assessinfo/{parcel_clean}/2025/0000"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(" ", strip=True)
            result["document_number"] = _extract_field(text, "Document Number")
            result["roll_category"]   = _extract_field(text, "Roll Category")
            result["situs_address"]   = _extract_field(text, "Address")
    except Exception:
        pass  # non-fatal — falls back to full-page scrape

def _extract_assessment_from_soup(soup: BeautifulSoup, result: dict):
    """Pull document number, roll category, address from assessment tab."""
    full_text = soup.get_text(" ", strip=True)
    result["document_number"] = _extract_field(full_text, "Document Number")
    result["roll_category"] = _extract_field(full_text, "Roll Category")
    result["situs_address"] = _extract_field(full_text, "Address")


# ─────────────────────────────────────────────
# FIELD EXTRACTOR
# ─────────────────────────────────────────────
def _extract_field(text: str, label: str) -> str | None:
    """Extract value following a label in flat text."""
    pattern = re.escape(label) + r"\s*[:\s]\s*([^\n$,]{1,60})"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


# ─────────────────────────────────────────────
# RESULT DERIVATION ENGINE
# ─────────────────────────────────────────────
def _derive_result(result: dict):
    paid_1 = (result.get("current_year_paid_1st") or "").upper()
    paid_2 = (result.get("current_year_paid_2nd") or "").upper()
    prior = result.get("prior_defaults", False)
    balance = result.get("portal_total_balance") or ""

    balance_float = 0.0
    try:
        balance_float = float(re.sub(r"[^0-9.]", "", balance))
    except Exception:
        pass

    fields_populated = sum([
        1 if paid_1 else 0,
        1 if paid_2 else 0,
        1 if result.get("first_total_due") else 0,
        1 if result.get("portal_total_balance") else 0,
        1 if result.get("document_number") else 0,
        1 if result.get("situs_address") else 0,
    ])
    completeness = round((fields_populated / 6) * 100)

    if "LATE" in paid_1 or "LATE" in paid_2 or balance_float > 0:
        result["portal_status"] = "DELINQUENT"
        result["verification_result"] = "HOT"
        reasons = []
        if "LATE" in paid_1:
            reasons.append(f"1st installment unpaid (delinquent {result.get('first_delinq_date','unknown')})")
        if "LATE" in paid_2:
            reasons.append(f"2nd installment unpaid (delinquent {result.get('second_delinq_date','unknown')})")
        if prior:
            reasons.append("Prior year defaults also exist")
        result["verification_reason"] = ". ".join(reasons) + f". Balance: {balance}."
        result["confidence_pct"] = min(99, completeness + 10) if completeness >= 50 else completeness

    elif "PAID" in paid_1 and "PAID" in paid_2 and prior:
        result["portal_status"] = "PAID_WITH_DEFAULTS"
        result["verification_result"] = "WARM"
        result["verification_reason"] = (
            f"Current year taxes paid (1st: {result.get('first_paid_date','?')}, "
            f"2nd: {result.get('second_paid_date','?')}). Prior year defaults remain unresolved."
        )
        result["confidence_pct"] = completeness

    elif "PAID" in paid_1 and "PAID" in paid_2:
        result["portal_status"] = "PAID_CURRENT"
        result["verification_result"] = "COLD"
        result["verification_reason"] = (
            f"Current year fully paid. No prior defaults detected. "
            f"Remove from active outreach."
        )
        result["confidence_pct"] = completeness

    else:
        result["portal_status"] = "INDETERMINATE"
        result["verification_result"] = "REVIEW"
        result["verification_reason"] = "Could not determine payment status — manual review required."
        result["confidence_pct"] = max(10, completeness - 20)


def compute_verified_score(original_score: float, confidence_pct: float, result: str) -> float:
    multipliers = {"HOT": 1.0, "WARM": 0.6, "COLD": 0.0, "REVIEW": 0.4, "ERROR": 0.2}
    m = multipliers.get(result, 0.2)
    raw = original_score * (confidence_pct / 100) * m
    return round(raw, 2)


# ─────────────────────────────────────────────
# AUDIT CSV WRITER
# ─────────────────────────────────────────────
def _write_audit_csv(records: list[dict], output_path: str):
    """Write full audit export — every field, every value."""
    if not records:
        return
    all_keys = list(records[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(f"\n[Audit Export] Written -> {output_path} ({len(records)} rows)")


# ─────────────────────────────────────────────
# CRM CSV WRITER
# ─────────────────────────────────────────────
CRM_FIELDS = [
    ("Lead Name",           "raw_owner"),
    ("Property Address",    "v_situs_address"),
    ("Parcel",              "apn"),
    ("Original Score",      "final_score"),
    ("Verified Score",      "v_verified_score"),
    ("Current Balance",     "v_portal_total_balance"),
    ("1st Installment Due", "v_first_total_due"),
    ("2nd Installment Due", "v_second_total_due"),
    ("1st Delinq Date",     "v_first_delinq_date"),
    ("2nd Delinq Date",     "v_second_delinq_date"),
    ("Prior Defaults",      "v_prior_defaults"),
    ("Document Number",     "v_document_number"),
    ("Roll Category",       "v_roll_category"),
    ("Lead Category",       "v_verification_result"),
    ("Portal Status",       "v_portal_status"),
    ("Confidence %",        "v_confidence_pct"),
    ("Reason",              "v_verification_reason"),
    ("Verified At",         "v_verified_at"),
    ("Portal URL",          "v_portal_url"),
    # Placeholders for enrichment fields you add later
    ("Mailing Address",     "mailing_address"),
    ("Phone",               "phone"),
    ("Email",               "email"),
    ("Notes",               "headline"),
]

def _write_crm_csv(records: list[dict], output_path: str):
    """Write sales-ready CRM export — one row per lead, only HOT and WARM."""
    crm_records = []
    for r in records:
        result = r.get("v_verification_result", "")
        if result not in ("HOT", "WARM", "REVIEW"):
            continue  # suppress COLD and ERROR from CRM view
        row = {}
        for crm_label, source_key in CRM_FIELDS:
            row[crm_label] = r.get(source_key, "")
        crm_records.append(row)

    crm_records.sort(key=lambda x: float(x.get("Verified Score") or 0), reverse=True)

    fieldnames = [f[0] for f in CRM_FIELDS]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(crm_records)
    print(f"[CRM Export]   Written -> {output_path} ({len(crm_records)} leads)")


# ─────────────────────────────────────────────
# SUMMARY REPORT
# ─────────────────────────────────────────────
def print_summary(records: list[dict]):
    total = len(records)
    counts = {"HOT": 0, "WARM": 0, "COLD": 0, "REVIEW": 0, "ERROR": 0}
    for r in records:
        k = r.get("v_verification_result", "ERROR")
        counts[k] = counts.get(k, 0) + 1

    hot_balance = sum(
        float(re.sub(r"[^0-9.]", "", r.get("v_portal_total_balance") or "0") or 0)
        for r in records if r.get("v_verification_result") == "HOT"
    )

    print("\n" + "=" * 60)
    print("  VERIFICATION PIPELINE — SUMMARY REPORT")
    print("=" * 60)
    print(f"  Total records processed : {total}")
    print(f"  HOT  (delinquent)       : {counts['HOT']}")
    print(f"  WARM (paid + defaults)  : {counts['WARM']}")
    print(f"  COLD (fully paid)       : {counts['COLD']}")
    print(f"  REVIEW (indeterminate)  : {counts['REVIEW']}")
    print(f"  ERROR (fetch failed)    : {counts['ERROR']}")
    print(f"  Total verified balance  : ${hot_balance:,.2f}")
    print(f"  False positive rate     : {round((counts['COLD']/total)*100, 1)}%")
    print("=" * 60)
    print(f"  Run at: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60 + "\n")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python verifier.py <county> [input_csv] [audit_csv] [crm_csv]")
        print("Example: python verifier.py tehama")
        sys.exit(1)

    county      = sys.argv[1].lower()
    input_file  = sys.argv[2] if len(sys.argv) > 2 else "A_PLUS_TEHAMA_PROBABILISTIC.csv"
    audit_file  = sys.argv[3] if len(sys.argv) > 3 else "VERIFIED_AUDIT.csv"
    crm_file    = sys.argv[4] if len(sys.argv) > 4 else "VERIFIED_CRM.csv"

    if not Path(input_file).exists():
        print(f"ERROR: Input file not found: {input_file}")
        sys.exit(1)

    verified_records = []

    with open(input_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        all_records = list(reader)

    print(f"[Pipeline] Loaded {len(all_records)} records from {input_file}")
    print(f"[Pipeline] Starting portal verification for {county.upper()} — tax year {TAX_YEAR}")
    print("-" * 60)

    for i, record in enumerate(all_records):
        parcel_raw = record.get("apn", "").strip()
        if not parcel_raw:
            print(f"  [{i+1}/{len(all_records)}] SKIP — no APN")
            continue

        original_score = float(record.get("final_score", 0) or 0)
        print(f"  [{i+1}/{len(all_records)}] {parcel_raw}...", end=" ", flush=True)

        portal_data = scrape_parcel(parcel_raw, county)
        conf = portal_data.get("confidence_pct") or 0
        v_result = portal_data.get("verification_result") or "ERROR"
        portal_data["verified_score"] = compute_verified_score(original_score, conf, v_result)

        merged = {**record, **{f"v_{k}": v for k, v in portal_data.items()}}
        verified_records.append(merged)

        print(
            f"{v_result:6s} | "
            f"Balance: {portal_data.get('portal_total_balance') or '$0':>10} | "
            f"Confidence: {conf}%"
        )

        time.sleep(REQUEST_DELAY)

    _write_audit_csv(verified_records, audit_file)
    _write_crm_csv(verified_records, crm_file)
    print_summary(verified_records)
