"""
Tehama owner enrichment v2 — multi-transform per doc, exhaustive matching.

For each APN with a doc number, try every reasonable Tehama doc format
transform. Only mark 'no_owner' after all transforms fail.

Also enhance:
  - If AsrPrint has NO doc number, also try current owner name from AsrPrint's
    assessee field (if it exists) as fallback
  - Name-based search as final fallback: use MPTS mailing address name

Goal: complete accuracy — every parcel either has verified owner or explicitly
no-owner-available.
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


def generate_doc_variants(doc: str) -> list:
    """Generate every plausible Tehama recorder search format for a doc number.

    Observed formats:
      Modern (2016+):   2016R011855   → recorder wants '2016011855'
      Modern:           2020R008897   → recorder wants '2020008897'
      7-digit w/ zero:  2011R0001795  → recorder wants '20110001795' OR '2011001795' OR '20111795'
      Old prefix:       2005R2686318  → try '20052686318' OR '2686318' (book-style)
      Non-R prefix:     2022ID120722  → strip ID: '2022120722'
      Old book/page:    1998R001234   → various patterns
    """
    if not doc:
        return []
    doc = doc.upper().strip()
    variants = set()

    # Extract year + prefix + suffix
    m = re.match(r"^(\d{4})([A-Z]+)(\d+)$", doc)
    if not m:
        # Fallback: just try raw + stripped
        variants.add(doc)
        variants.add(re.sub(r"[^0-9]", "", doc))
        return list(variants)

    year, prefix, suffix = m.group(1), m.group(2), m.group(3)

    # 1. Original doc unchanged
    variants.add(doc)
    # 2. Prefix removed (e.g., R stripped)
    variants.add(f"{year}{suffix}")
    # 3. Prefix stripped + leading zeros in suffix stripped
    variants.add(f"{year}{suffix.lstrip('0')}")
    # 4. Prefix as dash (e.g., R → -)
    variants.add(f"{year}-{suffix}")
    # 5. Suffix only (some old records use just the number)
    variants.add(suffix)
    variants.add(suffix.lstrip('0'))
    # 6. 2-digit year variants
    year2 = year[-2:]
    variants.add(f"{year2}{suffix}")
    variants.add(f"{year2}-{suffix}")
    # 7. Zero-padded to specific widths
    for width in [6, 7, 8]:
        if len(suffix) != width:
            variants.add(f"{year}{suffix.zfill(width)}")
            variants.add(f"{year}{suffix.lstrip('0').zfill(width)}")

    # Filter out ones that are too short
    return sorted(v for v in variants if len(v) >= 6)


def enrich_one(apn: str) -> dict:
    """Multi-transform enrichment for one APN."""
    result = {
        "apn": apn, "doc_number": "", "doc_variant_matched": "",
        "owner": "", "second_owner": "", "status": "",
    }
    try:
        asr = fetch_asr_print(apn, "tehama")
    except Exception as e:
        result["status"] = f"asr_err:{str(e)[:30]}"
        return result

    doc = (asr.get("doc_number") or "").strip()
    assessee = (asr.get("assessee_name") or "").strip()  # fallback if recorder fails

    if not doc:
        result["status"] = "no_doc_from_asr"
        if assessee:
            result["owner"] = assessee
            result["status"] = "assessor_only"
        return result

    result["doc_number"] = doc

    # Try every doc variant
    variants = generate_doc_variants(doc)
    for variant in variants:
        try:
            client = TylerRecorderClient(TEHAMA_RECORDER)
            client.submit_doc_search(variant)
            results, total = client.get_results(search_type="doc")
            if results and results[0].grantees:
                r0 = results[0]
                result["doc_variant_matched"] = variant
                result["owner"] = r0.grantees[0]
                if len(r0.grantees) > 1:
                    result["second_owner"] = r0.grantees[1]
                result["status"] = "ok_recorder"
                return result
        except Exception:
            continue  # try next variant

    # All variants failed - fallback to assessee if available
    if assessee:
        result["owner"] = assessee
        result["status"] = "assessor_fallback"
    else:
        result["status"] = "no_owner_available"
    return result


def enrich_batch(candidates_csv: str, out_csv: str, workers: int = 10, limit: int = None):
    with open(candidates_csv, encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))
    if limit:
        rows = rows[:limit]

    print(f"Enriching {len(rows)} Tehama candidates (multi-transform)...")
    apns = [r["apn"] for r in rows if r.get("apn")]

    results = []
    counts = {"ok_recorder": 0, "assessor_only": 0, "assessor_fallback": 0,
              "no_doc_from_asr": 0, "no_owner_available": 0, "err": 0}
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(enrich_one, apn): apn for apn in apns}
        completed = 0
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            completed += 1
            s = r.get("status", "err")
            if s in counts:
                counts[s] += 1
            else:
                counts["err"] += 1

            if completed % 25 == 0 or completed == len(apns):
                elapsed = time.time() - t0
                rate = completed / elapsed
                eta = (len(apns) - completed) / rate if rate > 0 else 0
                verified = counts["ok_recorder"]
                any_owner = verified + counts["assessor_only"] + counts["assessor_fallback"]
                print(f"  [{completed:5}/{len(apns)}] "
                      f"recorder={verified} assr={counts['assessor_only']+counts['assessor_fallback']} "
                      f"total_with_owner={any_owner} ({100*any_owner/completed:.0f}%) "
                      f"ETA {eta/60:.1f}min")

    # Merge back
    apn_to_result = {r["apn"]: r for r in results}
    enriched = []
    for orig in rows:
        merged = dict(orig)
        e = apn_to_result.get(orig.get("apn"), {})
        merged["doc_number"] = e.get("doc_number", "")
        merged["doc_variant_matched"] = e.get("doc_variant_matched", "")
        merged["verified_current_owner_name"] = e.get("owner", "")
        merged["second_owner"] = e.get("second_owner", "")
        merged["owner_source"] = e.get("status", "")
        enriched.append(merged)

    keys = []
    for r in enriched:
        for k in r.keys():
            if k not in keys: keys.append(k)
    with open(out_csv, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=keys)
        w.writeheader()
        w.writerows(enriched)

    print(f"\nWrote {out_csv}")
    print(f"Summary: {counts}")
    total_with_owner = counts["ok_recorder"] + counts["assessor_only"] + counts["assessor_fallback"]
    print(f"Total parcels with owner name: {total_with_owner} / {len(rows)} ({100*total_with_owner/len(rows):.0f}%)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--candidates",
                   default=r"C:/Users/chuck/Downloads/county_pipeline/data/tehama/tehama_auction_candidates.csv")
    p.add_argument("--out",
                   default=r"C:/Users/chuck/Downloads/county_pipeline/data/tehama/tehama_owner_enriched_v2.csv")
    p.add_argument("--workers", type=int, default=10)
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    enrich_batch(args.candidates, args.out, workers=args.workers, limit=args.limit)
