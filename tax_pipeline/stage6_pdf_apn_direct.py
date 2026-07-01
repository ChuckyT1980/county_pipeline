#!/usr/bin/env python3
"""
stage6_pdf_apn_direct.py

For the 107 power-to-sell APNs NOT in the audit file:
- Takes APNs directly from the legal publication PDF
- Skips Stage 1 discovery entirely (we already have the APN)
- Hits the MBC tax detail endpoint directly per APN
- Outputs: tehama_pdf_direct_leads.csv (107 records with live tax data + owner name)
"""

import re
import csv
import time
import requests
import pdfplumber
from datetime import datetime, timezone

COUNTY   = "tehama"
HOST     = "common1.mptsweb.com"
PDF_PATH = "June-8th-LEGAL-PUBLICATION-2025-Notice-of-Property-Tax-Delinquency-and-Impending-Default.pdf"
AUDIT_CSV   = "tehama_audit_20260627_024321.csv"   # your full 7743-row file
OUTPUT_CSV  = "tehama_pdf_direct_leads.csv"
TAX_YEAR    = "2025"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": f"https://{HOST}/MBC/{COUNTY}/tax/search",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
}

APN_RE   = re.compile(r'(\d{3}-\d{3}-\d{3}-\d{3})')
OWNER_RE = re.compile(
    r'(\d{3}-\d{3}-\d{3}-\d{3})\s+(.+?)\s+([\d,]+\.\d{2})\s*$'
)
YEAR_RE  = re.compile(r'PROPERTY TAX DEFAULTED ON JULY 1[,\s]+(\d{4})', re.I)

def normalize(apn): return apn.replace("-","").strip().zfill(12)

def extract_pdf_records(pdf_path):
    records = {}
    year = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").split("\n"):
                ym = YEAR_RE.search(line)
                if ym: year = ym.group(1); continue
                dm = OWNER_RE.search(line)
                if dm:
                    apn = dm.group(1)
                    assessee = dm.group(2).strip()
                    amt = dm.group(3)
                    addr_m = re.search(
                        r'(\d+\s+[A-Z0-9\s]+(?:RD|DR|AVE|ST|LN|WAY|HWY|BLVD|CT|PL|CIR|TR|LOOP|BEND)[A-Z0-9\s]*)',
                        assessee, re.I)
                    situs = ""
                    if addr_m:
                        situs = addr_m.group(1).strip()
                        assessee = assessee.replace(situs,"").strip()
                    records[normalize(apn)] = {
                        "apn_pdf": apn, "assessee_name": assessee,
                        "situs_pdf": situs, "amt_due_june2025": amt,
                        "default_year": year
                    }
    return records

def get_existing_apns(audit_csv):
    existing = set()
    try:
        with open(audit_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for k in ["feeparcel","asmt","fee_parcel"]:
                    if row.get(k):
                        existing.add(normalize(row[k]))
                        break
    except: pass
    return existing

def fetch_tax_detail(session, asmt_norm):
    """Hit MBC tax main endpoint directly with the APN."""
    # Format APN without dashes for URL
    a = asmt_norm.zfill(12)
    url = f"https://{HOST}/MBC/{COUNTY}/tax/main/{a}/{TAX_YEAR}/0000"
    try:
        resp = session.get(url, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            # Parse installment data from HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            lines = [ln.strip() for ln in soup.get_text("\n").split("\n") if ln.strip()]
            
            def val_after(keyword, search_lines):
                for i, ln in enumerate(search_lines):
                    if keyword.lower() in ln.lower():
                        for j in range(i + 1, min(i + 5, len(search_lines))):
                            candidate = search_lines[j]
                            if candidate and candidate.lower() != keyword.lower():
                                return candidate
                return None

            it = next((i for i, l in enumerate(lines) if "totals" in l.lower()), None)
            total_bal = 0.0
            status = "UNKNOWN"
            if it is not None:
                bt = lines[it: it + 20]
                bal_str = val_after("Total Balance", bt) or val_after("Balance", bt)
                if bal_str:
                    try:
                        total_bal = float(re.sub(r"[^\d.]", "", bal_str))
                    except: pass
            
            status_str = val_after("Paid Status", lines)
            if status_str:
                status = status_str
                
            return {
                "live_total_balance": f"{total_bal:.2f}",
                "live_paid_status": status,
                "live_tax_url": url,
                "live_verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
    except Exception as e:
        pass
    return {
        "live_total_balance": "", "live_paid_status": "ERROR",
        "live_tax_url": url, "live_verified_at": ""
    }

def run():
    print("[Stage 6] Extracting PDF records...")
    pdf_records = extract_pdf_records(PDF_PATH)
    print(f"  PDF total: {len(pdf_records)} APNs")

    existing = get_existing_apns(AUDIT_CSV)
    print(f"  Already in audit: {len(existing)} APNs")

    unmatched = {k:v for k,v in pdf_records.items() if k not in existing}
    print(f"  Unmatched (to fetch live): {len(unmatched)} APNs")

    session = requests.Session()
    results = []

    for i, (norm_apn, rec) in enumerate(unmatched.items()):
        print(f"  [{i+1}/{len(unmatched)}] {rec['apn_pdf']} {rec['assessee_name'][:30]}...", end=" ")
        live = fetch_tax_detail(session, norm_apn)
        results.append({**rec, **live, "source": "PDF_DIRECT"})
        print(f"bal=${live['live_total_balance']} status={live['live_paid_status']}")
        time.sleep(0.4)

    if results:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
        print(f"\n[Stage 6] Done. {len(results)} records -> {OUTPUT_CSV}")

    # Summary
    redeemed  = sum(1 for r in results if "PAID" in r.get("live_paid_status","").upper())
    still_due = len(results) - redeemed
    print(f"[Stage 6] Still delinquent: {still_due} | Redeemed since PDF: {redeemed}")

if __name__ == "__main__":
    run()
