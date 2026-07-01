#!/usr/bin/env python3
"""
Stage 4: Owner Enrichment Pipeline
Tehama County Tax Delinquency Lead System

Inputs:  crm_leads.csv (HOT/WARM parcels from Stage 3)
Outputs: crm_leads_enriched.csv (adds owner, mailing_addr, doc_number, doc_date, property_type, acres, assessed_value)

Sources (in priority order):
  1. MBAP AsrPrint  → doc_number, doc_date, property details (no headers needed)
  2. Regrid Free API → owner_name, mailing_address (free tier, no key needed for basic data)
  3. Fallback tag    → flag for manual skip trace
"""

import requests
import pandas as pd
from bs4 import BeautifulSoup
import time
import re
import json
import logging
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('stage4_enrich.log'),
        logging.StreamHandler()
    ]
)

# ─── County Config ───────────────────────────────────────────────────────────
COUNTY_CONFIG = {
    "tehama": {
        "mbap_host": "https://common1.mptsweb.com",
        "mbap_slug": "tehama",
        "mbc_host": "https://common1.mptsweb.com",
        "mbc_slug": "tehama",
        "state": "CA",
        "fips": "06103",
    },
    "shasta": {
        "mbap_host": "https://common2.mptsweb.com",
        "mbap_slug": "shasta",
        "mbc_host": "https://common2.mptsweb.com",
        "mbc_slug": "shasta",
        "state": "CA",
        "fips": "06089", # Shasta FIPS
    }
}

DELAY      = 0.75   # seconds between requests
TIMEOUT    = 15

# Global session init (we'll update referer per-county later)
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Accept":     "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

# ─── MBAP AsrPrint Parser ─────────────────────────────────────────────────────
def fetch_asr_print(apn: str, county: str) -> dict:
    cfg = COUNTY_CONFIG[county]
    session.headers.update({"Referer": f"{cfg['mbap_host']}/mbap/{cfg['mbap_slug']}/asr"})
    
    result = {
        "apn": apn,
        "doc_number": None,
        "doc_date": None,
        "property_type": None,
        "lot_acres": None,
        "net_assessed_value": None,
        "legal_desc": None,
        "situs_full": None,
        "asmt_status": None,
        "asrprint_url": "",
        "asrprint_status": "PENDING",
    }
    
    compact = str(apn).replace("-", "").strip()
    if len(compact) != 12:
        result["asrprint_status"] = "INVALID_APN"
        return result
        
    url = f"{cfg['mbap_host']}/mbap/{cfg['mbap_slug']}/asr/AsrPrint/{compact}"
    result["asrprint_url"] = url
    
    try:
        resp = session.get(url, timeout=TIMEOUT)
        if resp.status_code != 200:
            result["asrprint_status"] = f"HTTP_{resp.status_code}"
            return result
        
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.find_all("tr")
        data = {}
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                data[label] = value
        
        result["doc_number"]          = data.get("Current Document Number")
        result["doc_date"]            = data.get("Current Document Date") or data.get("Current Document  Date")
        result["property_type"]       = data.get("Property Type")
        result["lot_acres"]           = data.get("Lot Size(Acres)")
        result["legal_desc"]          = data.get("Asmt Description")
        result["situs_full"]          = data.get("SitusAddr")
        result["asmt_status"]         = data.get("Asmt Status")
        result["net_assessed_value"]  = data.get("Net Assessed Value")
        result["asrprint_status"]     = "OK"
        
        logging.info(f"AsrPrint OK: {apn} -> doc={result['doc_number']} type={result['property_type']}")
        
    except Exception as e:
        result["asrprint_status"] = f"ERROR: {e}"
        logging.warning(f"AsrPrint FAILED for {apn}: {e}")
    
    return result

# ─── Tax Bill Mailing Address Parser ─────────────────────────────────────────
def fetch_mailing_address(asmt: str, roll_cat: str, county: str) -> dict:
    cfg = COUNTY_CONFIG[county]
    session.headers.update({"Referer": f"{cfg['mbc_host']}/mbc/{cfg['mbc_slug']}/tax/search"})
    
    roll_type = "S" if roll_cat.endswith("S") else "U"
    asmt_clean = asmt.replace("-", "").replace(" ", "").zfill(12)
    
    url = (
        f"https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx"
        f"?CN={cfg['mbc_slug']}&Asmt={asmt_clean}&TaxYear=2025"
        f"&RollCat={roll_cat}&RollType={roll_type}&RollYear="
    )
    
    result = {
        "mailing_address_raw": None,
        "taxbill_url": url,
        "taxbill_status": "PENDING",
    }
    
    try:
        resp = session.get(url, timeout=TIMEOUT)
        if resp.status_code != 200:
            result["taxbill_status"] = f"HTTP_{resp.status_code}"
            return result
        
        soup = BeautifulSoup(resp.text, "html.parser")
        full_text = soup.get_text(separator="\n")
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]
        
        addr_lines = []
        capture = False
        for line in lines:
            if "LOCATION:" in line or line.startswith("LOCATION"):
                capture = True
                continue
            if capture:
                if re.match(r"^\d{4}-\d{4}$", line) or "COUNTY VALUES" in line:
                    break
                if line and not line.startswith("DUPLICATE") and not line.startswith("IMPORTANT"):
                    addr_lines.append(line)
        
        if addr_lines:
            result["mailing_address_raw"] = " | ".join(addr_lines[:4])
            result["taxbill_status"] = "OK"
        else:
            result["taxbill_status"] = "NO_ADDR_FOUND"
        
    except Exception as e:
        result["taxbill_status"] = f"ERROR: {e}"
        logging.warning(f"TaxBill FAILED for {asmt}: {e}")
    
    return result

# ─── Regrid Free Lookup ────────────────────────────────────────
def fetch_regrid_owner(apn: str, state_fips: str = "06103") -> dict:
    result = {
        "regrid_owner": None,
        "regrid_mailing": None,
        "regrid_status": "PENDING",
    }
    url = f"https://app.regrid.com/api/v1/parcel.json"
    params = {
        "parcelnumb": apn.zfill(12),
        "state_fips": "06",
        "county_fips": state_fips,
    }
    headers_regrid = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://app.regrid.com/",
    }
    
    try:
        resp = requests.get(url, params=params, headers=headers_regrid, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            features = data.get("results", {}).get("features", [])
            if features:
                props = features[0].get("properties", {}).get("fields", {})
                result["regrid_owner"]   = props.get("owner")
                result["regrid_mailing"] = props.get("mailadd")
                result["regrid_status"]  = "OK"
            else:
                result["regrid_status"] = "NO_RESULTS"
        else:
            result["regrid_status"] = f"HTTP_{resp.status_code}"
    except Exception as e:
        result["regrid_status"] = f"ERROR: {e}"
    
    return result

# ─── Main Enrichment Loop ─────────────────────────────────────────────────────
def main(input_csv: str):
    import os
    basename = os.path.basename(input_csv).lower()
    county = "tehama"
    if "shasta" in basename:
        county = "shasta"
    
    logging.info(f"Starting Stage 4 Enrichment for {county.upper()} on {input_csv} | {datetime.now().isoformat()} ===")
    
    df = pd.read_csv(input_csv)
    logging.info(f"Loaded {len(df)} CRM leads from {input_csv}")
    
    apn_col = None
    for candidate in ["apn", "fee_parcel", "parcel", "APN", "FEE_PARCEL"]:
        if candidate in df.columns:
            apn_col = candidate
            break
    if apn_col is None:
        raise ValueError(f"Cannot find APN column. Available: {list(df.columns)}")
    
    asmt_col = None
    for candidate in ["asmt", "assessment_number", "ASMT", "asmt_number"]:
        if candidate in df.columns:
            asmt_col = candidate
            break
    
    enriched_rows = []
    
    for i, row in df.iterrows():
        apn  = str(row[apn_col]).strip().replace(".0", "")
        if apn.lower() in ("nan", "none", ""):
            apn = str(row.get("apn_pdf", "")).strip()
        
        asmt = str(row[asmt_col]).strip().replace(".0", "") if asmt_col else apn
        if asmt.lower() in ("nan", "none", ""):
            asmt = apn
        
        logging.info(f"[{i+1}/{len(df)}] Processing APN: {apn}")
        
        asr_data = fetch_asr_print(apn, county)
        time.sleep(DELAY)
        
        roll_cat = str(row.get("roll_cat", "CS")).strip() or "CS"
        bill_data = fetch_mailing_address(asmt, roll_cat, county)
        time.sleep(DELAY)
        
        regrid_data = fetch_regrid_owner(apn)
        time.sleep(DELAY)
        
        owner_name    = regrid_data.get("regrid_owner") or "SKIP_TRACE_REQUIRED"
        mailing_addr  = (
            regrid_data.get("regrid_mailing")
            or bill_data.get("mailing_address_raw")
            or "UNKNOWN"
        )
        
        enriched_row = {
            **row.to_dict(),
            "rec_doc_number":     asr_data.get("doc_number"),
            "rec_doc_date":       asr_data.get("doc_date"),
            "property_type":      asr_data.get("property_type"),
            "lot_acres":          asr_data.get("lot_acres"),
            "legal_desc":         asr_data.get("legal_desc"),
            "net_assessed_value": asr_data.get("net_assessed_value"),
            "asmt_status":        asr_data.get("asmt_status"),
            "asrprint_url":       asr_data.get("asrprint_url"),
            "address":            asr_data.get("situs_full"),
            "address_source":     "assessor" if asr_data.get("situs_full") else "none",
            "address_fetch_time": datetime.now().isoformat(),
            "owner_name":         owner_name,
            "mailing_address":    mailing_addr,
            "owner_source":       (
                "REGRID" if regrid_data.get("regrid_owner")
                else "TAXBILL" if bill_data.get("mailing_address_raw")
                else "NONE"
            ),
            "asrprint_status":    asr_data.get("asrprint_status"),
            "taxbill_status":     bill_data.get("taxbill_status"),
            "regrid_status":      regrid_data.get("regrid_status"),
        }
        enriched_rows.append(enriched_row)
        
    out_csv = input_csv.replace(".csv", "_enriched.csv")
    out_df = pd.DataFrame(enriched_rows)
    out_df.to_csv(out_csv, index=False)
    logging.info(f"Saved {len(out_df)} enriched leads to {out_csv}")
    print(f"\n[OK] Enrichment complete. Saved to {out_csv}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stage4_owner_enrich.py <leads_csv>")
        sys.exit(1)
    main(sys.argv[1])
