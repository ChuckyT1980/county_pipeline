import os
import re
import sys
import time
from datetime import datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup

# --- Config ---
COUNTY_SLUG = "shasta"
BASE_URL = "https://common2.mptsweb.com"  # Shasta is on common2
TAX_YEAR = "2025"

def get_raw_asmt(apn: str) -> str:
    return re.sub(r"[^\d]", "", str(apn)).zfill(12)

def parse_dollar(s) -> float:
    if not s:
        return 0.0
    try:
        return float(re.sub(r"[^\d.]", "", str(s)))
    except:
        return 0.0

def val_after(keyword, search_lines):
    for i, ln in enumerate(search_lines):
        if keyword.lower() in ln.lower():
            for j in range(i + 1, min(i + 5, len(search_lines))):
                candidate = search_lines[j]
                if candidate and candidate.lower() != keyword.lower():
                    return candidate
    return None

def fetch_tax_data(session, asmt_raw: str):
    out = {
        "verified_url": f"{BASE_URL}/MBC/{COUNTY_SLUG}/tax/main/{asmt_raw}/{TAX_YEAR}/0000",
        "verified_at": datetime.utcnow().isoformat(),
        "v_total_due": None,
        "v_total_paid": None,
        "v_total_balance": None,
        "v_delinquent": False,
        "v_document_number": None,
        "owner_name": None,
        "error": None
    }
    
    # 1. Fetch Owner Name from AsrPrint
    try:
        asr_url = f"{BASE_URL}/mbap/{COUNTY_SLUG}/asr/AsrPrint/{asmt_raw}"
        asr_resp = session.get(asr_url, timeout=10)
        if asr_resp.status_code == 200:
            soup = BeautifulSoup(asr_resp.text, "html.parser")
            for tr in soup.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    if label in ("Assessee Name", "Owner", "Assessee", "Owner Name"):
                        out["owner_name"] = cells[1].get_text(strip=True)
                        break
    except Exception as e:
        out["error"] = f"AsrPrint Error: {e}"

    # 2. Fetch Tax Balance from Main Tax Page
    try:
        resp = session.get(out["verified_url"], timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        lines = [ln.strip() for ln in soup.get_text("\n").split("\n") if ln.strip()]
        
        it = next((i for i, l in enumerate(lines) if "totals" in l.lower()), None)
        if it is not None:
            bt = lines[it: it + 20]
            out["v_total_due"]     = val_after("Total Due", bt)
            out["v_total_paid"]    = val_after("Total Paid", bt)
            out["v_total_balance"] = val_after("Total Balance", bt) or val_after("Balance", bt)

        out["v_document_number"] = val_after("Document Number", lines)

        i1 = next((i for i, l in enumerate(lines) if l.lower() == "installment" and i >= 2 and lines[i-2] == "1" and lines[i-1].lower() == "st"), None)
        i2 = next((i for i, l in enumerate(lines) if l.lower() == "installment" and i >= 2 and lines[i-2] == "2" and lines[i-1].lower() == "nd"), None)
        
        for idx in [i1, i2]:
            if idx is not None:
                block = lines[idx: idx + 20]
                status = val_after("Paid Status", block)
                if status and any(kw in str(status).upper() for kw in ["DELINQUENT", "UNPAID", "PAST DUE", "DEFAULTED", "LATE"]):
                    out["v_delinquent"] = True

    except Exception as e:
        if not out["error"]: out["error"] = ""
        out["error"] += f" | TaxPage Error: {e}"

    return out

def run_stage1(input_csv, max_records=None):
    print(f"Starting Stage 1 Tax Verification on {input_csv}...")
    df = pd.read_csv(input_csv)
    
    if max_records:
        df = df.head(max_records)
    
    checkpoint_file = input_csv.replace('.csv', '_VERIFIED_partial.parquet')
    processed_apns = set()
    results = []
    
    if os.path.exists(checkpoint_file):
        existing_df = pd.read_parquet(checkpoint_file)
        results = existing_df.to_dict("records")
        processed_apns = set(existing_df["parcel_number"].dropna().tolist())
        print(f"Resuming from checkpoint: {len(processed_apns)} already processed.")
    
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    
    for i, row in df.iterrows():
        apn = row.get("parcel_number", "")
        
        if not apn or pd.isna(apn) or apn in processed_apns:
            continue
            
        asmt_raw = get_raw_asmt(apn)
        
        print(f"Verifying {apn} ({i+1}/{len(df)})...", end=" ")
        
        tax_data = fetch_tax_data(session, asmt_raw)
        
        combined = {**row.to_dict(), **tax_data}
        results.append(combined)
        processed_apns.add(apn)
        
        bal = combined["v_total_balance"] or "0.00"
        delinq = "YES" if combined["v_delinquent"] else "NO"
        doc = combined["v_document_number"] or "NO_DOC"
        
        print(f"Doc: {doc[:15].ljust(15)} | Bal: ${bal} | Delinquent: {delinq}")
        
        if len(processed_apns) % 50 == 0:
            pd.DataFrame(results).to_parquet(checkpoint_file)
            print(f"--> Checkpointed {len(processed_apns)} records.")
            
        time.sleep(0.3)
        
    out_df = pd.DataFrame(results)
    if max_records:
        out_name = input_csv.replace(".csv", "_TEST_VERIFIED.csv")
    else:
        out_name = input_csv.replace(".csv", "_VERIFIED.csv")
        
    out_df.to_csv(out_name, index=False)
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
    print(f"Saved {len(out_df)} verified records to {out_name}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run only first 10 records")
    parser.add_argument("input_csv", nargs="?", default=os.path.join(os.path.dirname(__file__), "shasta_15_percent_sample.csv"))
    args = parser.parse_args()
    
    if args.test:
        run_stage1(args.input_csv, max_records=10)
    else:
        run_stage1(args.input_csv)
