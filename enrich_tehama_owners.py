"""
Enrich Tehama candidates with owner names via Tyler recorder lookup.

Flow per APN:
  1. Hit MPTS AsrPrint → get Current Document Number
  2. Transform doc number (Tehama needs R stripped: 2026R006490 → 2026006490)
  3. Look up doc in Tehama Tyler recorder → grantees (= current owners)
  4. Save enriched row

Reuses existing infrastructure:
  - tax_pipeline/stage4_owner_enrich.py → fetch_asr_print
  - tyler_recorder_client.py → TylerRecorderClient
"""
import argparse
import csv
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent))
from tax_pipeline.stage4_owner_enrich import fetch_asr_print
from tyler_recorder_client import TylerRecorderClient, CountyConfig

TEHAMA_RECORDER = CountyConfig(
    county="tehama",
    base_url="https://recordsearch.tehama.gov",
    name_search_id="DOCSEARCH4S1",
    doc_search_id="DOCSEARCH4S2",
    ajax_headers_required=True,
)


def _transform_doc(doc: str) -> str:
    """Tehama format: 2026R006490 -> 2026006490 (strip the R)."""
    if not doc:
        return ""
    return re.sub(r"R", "", doc.upper().strip())


def enrich_one(apn: str) -> dict:
    """Get doc number from MPTS, look up grantee from Tehama Tyler recorder."""
    result = {"apn": apn, "doc_number": "", "owner": "", "second_owner": "", "status": ""}

    # Step 1: MPTS AsrPrint for doc number
    try:
        asr = fetch_asr_print(apn, "tehama")
    except Exception as e:
        result["status"] = f"asr_err:{str(e)[:40]}"
        return result

    doc = (asr.get("doc_number") or "").strip()
    if not doc:
        result["status"] = "no_doc_from_asr"
        return result

    result["doc_number"] = doc
    doc_transformed = _transform_doc(doc)

    # Step 2: Tyler recorder lookup
    try:
        client = TylerRecorderClient(TEHAMA_RECORDER)
        client.submit_doc_search(doc_transformed)
        results, total = client.get_results(search_type="doc")
        if results:
            r = results[0]
            if r.grantees:
                result["owner"] = r.grantees[0]
                if len(r.grantees) > 1:
                    result["second_owner"] = r.grantees[1]
            result["status"] = "ok"
        else:
            result["status"] = "no_recorder_match"
    except Exception as e:
        result["status"] = f"recorder_err:{str(e)[:40]}"

    return result


def enrich_batch(candidates_csv: str, out_csv: str, workers: int = 15, limit: int = None):
    with open(candidates_csv, encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))
    if limit:
        rows = rows[:limit]

    print(f"Enriching {len(rows)} Tehama candidates with owner names...")
    apns = [r["apn"] for r in rows if r.get("apn")]

    results = []
    counts = {"ok": 0, "no_doc": 0, "no_match": 0, "err": 0}
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(enrich_one, apn): apn for apn in apns}
        completed = 0
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            completed += 1
            s = r.get("status", "?")
            if s == "ok": counts["ok"] += 1
            elif s == "no_doc_from_asr": counts["no_doc"] += 1
            elif s == "no_recorder_match": counts["no_match"] += 1
            else: counts["err"] += 1
            if completed % 25 == 0 or completed == len(apns):
                elapsed = time.time() - t0
                rate = completed / elapsed
                eta = (len(apns) - completed) / rate if rate > 0 else 0
                print(f"  [{completed:5}/{len(apns)}] ok={counts['ok']} no_doc={counts['no_doc']} no_match={counts['no_match']} err={counts['err']}  {rate:.1f} req/s  ETA {eta/60:.1f} min")

    # Merge back with the original candidate data
    apn_to_owner = {r["apn"]: r for r in results}
    enriched_rows = []
    for orig in rows:
        merged = dict(orig)
        e = apn_to_owner.get(orig.get("apn"), {})
        merged["doc_number"] = e.get("doc_number", "")
        merged["verified_current_owner_name"] = e.get("owner", "")
        merged["second_owner"] = e.get("second_owner", "")
        merged["owner_lookup_status"] = e.get("status", "")
        enriched_rows.append(merged)

    keys = []
    for r in enriched_rows:
        for k in r.keys():
            if k not in keys: keys.append(k)
    with open(out_csv, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=keys)
        w.writeheader()
        w.writerows(enriched_rows)

    print(f"\nWrote {out_csv}")
    print(f"Summary: ok={counts['ok']} no_doc={counts['no_doc']} no_recorder_match={counts['no_match']} err={counts['err']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--candidates",
                   default=r"C:/Users/chuck/Downloads/county_pipeline/data/tehama/tehama_auction_candidates.csv")
    p.add_argument("--out",
                   default=r"C:/Users/chuck/Downloads/county_pipeline/data/tehama/tehama_owner_enriched.csv")
    p.add_argument("--workers", type=int, default=15)
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    enrich_batch(args.candidates, args.out, workers=args.workers, limit=args.limit)
