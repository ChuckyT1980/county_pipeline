"""
fresno_recorder_pull.py

Pull recorded documents for every unique APN in the Fresno historical
sales dataset from the Tyler Technologies recorder portal, then derive
former-owner rows for the excess-proceeds recovery letters.

Usage:
    python fresno/fresno_recorder_pull.py [--csv fresno/fresno_historical_51_ENRICHED.csv]
                                          [--out fresno/fresno_recorder_apn_docs.csv]
                                          [--delay 1.0]
"""
import argparse
import csv
import json
import sys
import time

sys.path.insert(0, r"C:\Users\chuck\Downloads\county_pipeline")
from tyler_recorder_client import TylerRecorderClient, FRESNO, RecorderResult


def page_count_from_post(post_resp) -> int:
    try:
        data = json.loads(post_resp.text)
        return int(data.get("totalPages", 0))
    except (ValueError, AttributeError):
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=r"fresno\fresno_historical_51_ENRICHED.csv")
    ap.add_argument("--out", default=r"fresno\fresno_recorder_apn_docs.csv")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--max-apns", type=int, default=0)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8-sig")))
    seen: dict[str, dict] = {}
    for r in rows:
        apn = (r.get("APN") or "").strip()
        if not apn or apn in seen:
            continue
        seen[apn] = r
    apns = list(seen)
    if args.max_apns:
        apns = apns[: args.max_apns]
    print(f"{len(apns)} unique APNs to pull", flush=True)

    client = TylerRecorderClient(FRESNO, timeout=25.0, delay_between_requests=args.delay)
    out_rows = []
    failures = []
    try:
        for i, apn in enumerate(apns, 1):
            try:
                post_resp = client.submit_apn_search(apn)
                total_pages = page_count_from_post(post_resp)
                results: list[RecorderResult] = []
                for page in range(1, total_pages + 1):
                    page_results, _ = client.get_results(page=page, search_type="apn")
                    results.extend(page_results)
                    if page < total_pages:
                        time.sleep(args.delay)
                for res in results:
                    out_rows.append(
                        {
                            "APN": apn,
                            "doc_id": res.doc_id,
                            "doc_number": res.doc_number,
                            "doc_type": res.doc_type,
                            "recording_date": res.recording_date,
                            "grantors": " | ".join(res.grantors),
                            "grantees": " | ".join(res.grantees),
                        }
                    )
                print(f"[{i}/{len(apns)}] {apn}: {total_pages} pages, {len(results)} docs", flush=True)
            except Exception as exc:
                failures.append((apn, str(exc)))
                print(f"[{i}/{len(apns)}] {apn}: FAILED - {exc}", flush=True)
            time.sleep(args.delay)
    finally:
        client.close()

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["APN", "doc_id", "doc_number", "doc_type", "recording_date", "grantors", "grantees"]
        )
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nWrote {len(out_rows)} document rows to {args.out}")
    if failures:
        print(f"{len(failures)} failures:")
        for apn, err in failures:
            print(f"  {apn}: {err}")


if __name__ == "__main__":
    main()
