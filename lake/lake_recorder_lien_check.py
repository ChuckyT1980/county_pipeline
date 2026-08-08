"""
Lake County recorder-based lien-lifecycle check.

Resolves an ambiguity the MPTS assessor page cannot: whether a parcel listed
on the county's official TDLS164 tax-defaulted sale list (March 2026, now
concluded) is STILL tax-defaulted, was REDEEMED (owner paid off before/after
the sale — recorded as a "Release of Lien" back to the original owner), or
was SOLD at the sale (recorded as a new deed to a purchaser / tax deed).

Uses the real, confirmed-working Lake Tyler EagleWeb recorder
(lakecountyca-web.tylerhost.net), Official Records Search - Web
(DOCSEARCH4S3), field_ParcelID + recording-date-range search — genuinely
parcel-tied, not name-only. No CAPTCHA encountered past the disclaimer
accept (confirmed live 2026-08-08).
"""
import csv
import re
import time

import httpx
from bs4 import BeautifulSoup

BASE = "https://lakecountyca-web.tylerhost.net"


def new_client():
    c = httpx.Client(base_url=BASE, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    }, timeout=20, follow_redirects=True)
    c.get("/web/user/disclaimer")
    c.post("/web/user/disclaimer")
    c.get("/web/search/DOCSEARCH4S3")
    return c


def search_apn(client, apn_dash, start="01/01/2024", end="08/08/2026"):
    payload = {
        "field_ParcelID": apn_dash.replace("-", ""),
        "field_selfservice_documentTypes-containsInput": "Contains Any",
        "field_selfservice_documentTypes": "",
        "field_RecordingDateID_DOT_StartDate": start,
        "field_RecordingDateID_DOT_EndDate": end,
    }
    r = client.post("/web/searchPost/DOCSEARCH4S3", data=payload,
                     headers={"ajaxrequest": "true", "x-requested-with": "XMLHttpRequest",
                              "Accept": "application/json, text/javascript, */*; q=0.01"})
    r.raise_for_status()
    r2 = client.get("/web/searchResults/DOCSEARCH4S3",
                     headers={"ajaxrequest": "true", "x-requested-with": "XMLHttpRequest"},
                     params={"page": 1})
    r2.raise_for_status()
    return r2.text


def parse_results(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("li.ss-search-row")
    out = []
    for row in rows:
        header = row.select_one("h1")
        header_text = header.get_text(" ", strip=True) if header else ""
        segments = [s.strip() for s in header_text.split("•") if s.strip()]
        doc_number = segments[0] if segments else ""
        doc_type = segments[-1] if len(segments) > 1 else ""
        grantor, grantee, rec_date = None, None, None
        for col in row.select("div.searchResultThreeColumn"):
            lines = [li.get_text(strip=True) for li in col.select("li") if li.get_text(strip=True)]
            if not lines:
                continue
            label = lines[0].lower()
            val = lines[1] if len(lines) > 1 else None
            if "recording date" in label:
                rec_date = val
            elif "grantor" in label:
                grantor = val
            elif "grantee" in label:
                grantee = val
        out.append({"doc_number": doc_number, "doc_type": doc_type, "recording_date": rec_date,
                     "grantor": grantor, "grantee": grantee})
    return out


def classify(docs):
    """Classify a parcel's current status from its 2024-2026 document history."""
    types_seen = [(d["doc_type"] or "").upper() for d in docs]
    has_lien = any("TAX DEFAULT" in t and "LIEN" in t for t in types_seen)
    has_release = any("RELEASE" in t and "LIEN" in t for t in types_seen)
    # Real observed doc_type text is "DEED TAX" (word order: DEED then TAX,
    # e.g. "36 DEED TAX"), not "TAX DEED" -- confirmed live 2026-08-08
    # against real Lake recorder results (e.g. 002-023-380-000, sold,
    # recorded 06/05/2026 as "36 DEED TAX"). A bare "DEED" doc type
    # (exact match, not "DEED OF TRUST"/"RECONVEYANCE"/etc.) also signals
    # an ownership transfer.
    has_sale_deed = any("DEED TAX" in t for t in types_seen)
    has_any_deed_transfer = any(t == "DEED" for t in types_seen)

    if has_sale_deed:
        return "SOLD_AT_AUCTION"
    if has_release:
        return "REDEEMED"
    if has_any_deed_transfer:
        return "OWNERSHIP_TRANSFER_UNRELATED_TO_TAX_SALE"
    if has_lien:
        return "STILL_DEFAULTED_NO_RELEASE_FOUND"
    return "NO_RECENT_RECORDER_ACTIVITY_FOUND"


def main():
    import sys
    rows = list(csv.DictReader(open("lake/lake_TDLS164_parsed.csv", encoding="utf-8")))
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else len(rows)
    sample = rows[start:end]

    client = new_client()
    results = []
    for i, r in enumerate(sample):
        apn = r["apn"]
        try:
            html = search_apn(client, apn)
            docs = parse_results(html)
        except Exception as e:
            print(f"[{i+1}/{len(sample)}] {apn} ERROR: {e}")
            results.append({"apn": apn, "status": f"ERROR: {e}", "docs": ""})
            client = new_client()
            continue

        status = classify(docs)
        doc_summary = " | ".join(f"{d['doc_type']}({d['recording_date']})" for d in docs)
        print(f"[{i+1}/{len(sample)}] {apn}: {status} -- {doc_summary}")
        results.append({
            "apn": apn, "status": status, "min_bid": r["min_bid"], "source_situs": r["situs"],
            "docs_json": docs,
        })
        time.sleep(0.5)

    import json
    outpath = f"lake/lake_lien_classification_{start}_{end}.json"
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {outpath}")

    from collections import Counter
    c = Counter(r["status"] for r in results)
    print("\nSummary:", dict(c))


if __name__ == "__main__":
    main()
