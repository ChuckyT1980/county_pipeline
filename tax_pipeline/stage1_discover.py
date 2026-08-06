"""
Stage 1: Parcel discovery via feeparcel prefix enumeration.
Works when situs search is unavailable (or for counties that lack it).
Enumerates 6-digit APN prefixes (BBBPPP) via the feeparcel JSON API.

Incremental checkpointing: saves after every book in Phase 2.
Resume: run again with same output path — skips completed books.

Usage:
    python stage1_discover.py tehama [output_csv]
    python stage1_discover.py shasta [output_csv]
"""
import sys, os, json, re, time
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
from config import COUNTY_CONFIG

sys.stdout.reconfigure(line_buffering=True)

def get_parcels(session, api_base, prefix6):
    try:
        r = session.get(api_base + prefix6, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        if isinstance(data, str):
            data = json.loads(data)
        row = data.get("Table", {}).get("Row", [])
        if isinstance(row, list) and len(row) > 0 and row[0].get("Asmt") is not None:
            return row
    except Exception:
        pass
    return []

def norm(row, host, county):
    def g(*keys):
        for k in keys:
            v = row.get(k) or row.get(k.lower()) or row.get(k.upper())
            if v: return str(v).strip()
        return ""
    ac = re.sub(r"\D", "", g("Asmt", "asmt", "ASMT"))
    if not ac:
        return None
    a = f"{ac[0:3]}-{ac[3:6]}-{ac[6:9]}-{ac[9:12]}" if len(ac) == 12 else ac
    fp = g("FeeParcel", "feeparcel", "FeeParcel")
    if fp and re.match(r'^\d{12}$', fp):
        fp = f"{fp[0:3]}-{fp[3:6]}-{fp[6:9]}-{fp[9:12]}"
    return {
        "asmt": a, "asmt_raw": ac, "address": g("Situs1"),
        "year": "2025", "roll_year": "0000",
        "tra": g("Tra"), "roll_cat": g("RollCategory"),
        "fee_parcel": fp,
        "detail_url": f"{host}/MBC/{county}/tax/main/{ac}/2025/0000",
        "county": county, "discovered_at": datetime.utcnow().isoformat(),
    }

def discover(county, out_csv):
    cfg = COUNTY_CONFIG[county]
    host = cfg["host"]
    api_base = f"{host}/MBC/api/search/{county}/0000-CURR/feeparcel/"
    search_url = f"{host}/MBC/{county}/tax/search"

    ckpt_json = out_csv.replace(".csv", "_checkpoint.json")
    ckpt_csv  = out_csv.replace(".csv", "_partial.csv")

    S = requests.Session()
    retry_strategy = Retry(
        total=10, 
        backoff_factor=2, 
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    S.mount("https://", adapter)
    S.mount("http://", adapter)

    S.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    })
    S.get(search_url, timeout=15)
    S.headers["Referer"] = search_url
    time.sleep(1)

    print(f"\n[{county.upper()} DISCOVERY] -> {out_csv}", flush=True)
    print(f"  API base: {api_base}", flush=True)

    # ── Phase 1: find valid books ──
    valid_books = []
    if os.path.exists(ckpt_json):
        with open(ckpt_json) as f:
            meta = json.load(f)
            valid_books = meta.get("valid_books", [])
        if valid_books:
            print(f"[Resume] Phase 1 already done: {len(valid_books)} books", flush=True)

    if not valid_books:
        probes = ["050", "150", "250", "350", "450", "550"]
        seen_books = set()
        for pv in probes:
            for book in range(1000):
                p6 = f"{book:03d}{pv}"
                rows = get_parcels(S, api_base, p6)
                if rows:
                    seen_books.add(book)
                time.sleep(0.02)
            print(f"  Probe page={pv}: {len(seen_books)} unique books so far", flush=True)
        valid_books = sorted(seen_books)
        with open(ckpt_json, "w") as f:
            json.dump({"valid_books": valid_books, "completed_books": []}, f)
        print(f"  Valid books ({len(valid_books)}): {valid_books}", flush=True)
    else:
        with open(ckpt_json) as f:
            meta = json.load(f)
        completed = set(meta.get("completed_books", []))
        loaded_asmt = set()
        loaded_rows = []
        if os.path.exists(ckpt_csv):
            pdf = pd.read_csv(ckpt_csv)
            loaded_asmt = set(pdf["asmt_raw"].dropna().tolist()) if "asmt_raw" in pdf.columns else set()
            loaded_rows = pdf.to_dict("records")
            print(f"[Resume] Partial CSV loaded: {len(loaded_rows)} rows, {len(loaded_asmt)} ASMTs", flush=True)
        else:
            loaded_rows = []
        remaining = [b for b in valid_books if b not in completed]
        if remaining:
            print(f"[Resume] Skipping {len(completed)} completed books, {len(remaining)} remaining", flush=True)
        else:
            print(f"[Resume] All {len(completed)} books already completed", flush=True)
            if loaded_rows:
                df = pd.DataFrame(loaded_rows)
                df.to_csv(out_csv, index=False)
                print(f"  Final CSV assembled from partial: {len(df)} rows -> {out_csv}", flush=True)
            return

    # ── Phase 2: scan pages for each valid book ──
    loaded_asmt = set()
    loaded_rows = []
    if os.path.exists(ckpt_csv):
        pdf = pd.read_csv(ckpt_csv)
        loaded_asmt = set(pdf["asmt_raw"].dropna().tolist()) if "asmt_raw" in pdf.columns else set()
        loaded_rows = pdf.to_dict("records")
        print(f"  Partial CSV: {len(loaded_rows)} rows loaded", flush=True)

    meta = json.load(open(ckpt_json)) if os.path.exists(ckpt_json) else {"completed_books": []}
    completed = set(meta.get("completed_books", []))
    remaining_books = [b for b in valid_books if b not in completed]

    for book in remaining_books:
        for page in range(0, 1000, 10):
            p6 = f"{book:03d}{page:03d}"
            rows = get_parcels(S, api_base, p6)
            if rows:
                for r in rows:
                    aid = r.get("Asmt", "")
                    if aid and aid not in loaded_asmt:
                        n = norm(r, host, county)
                        if n:
                            loaded_asmt.add(aid)
                            loaded_rows.append(n)
                print(f"  {book:03d}-{page:03d}: +{len(rows)} (total: {len(loaded_rows)})", flush=True)
            time.sleep(0.02)

        pd.DataFrame(loaded_rows).to_csv(ckpt_csv, index=False)
        completed.add(book)
        with open(ckpt_json, "w") as f:
            json.dump({"valid_books": valid_books, "completed_books": sorted(completed)}, f)
        print(f"  [Checkpoint] Book {book:03d} done. Total: {len(loaded_rows)} rows -> {ckpt_csv}", flush=True)

    df = pd.DataFrame(loaded_rows)
    df.to_csv(out_csv, index=False)
    print(f"\nDONE: {len(df)} unique {county} parcels -> {out_csv}", flush=True)

    for cp in [ckpt_json, ckpt_csv]:
        try:
            os.remove(cp)
        except:
            pass

if __name__ == "__main__":
    county = sys.argv[1].lower() if len(sys.argv) > 1 else "tehama"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    discover(county, sys.argv[2] if len(sys.argv) > 2 else f"{county}_discovery_{ts}.csv")
