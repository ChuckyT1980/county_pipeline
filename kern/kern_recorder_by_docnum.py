"""
Real, parcel-tied Kern recorder verification via document-number search
(https://recorderonline.co.kern.ca.us/cgi-bin/Osearchn.mbr/input) —
genuinely superior to the earlier grantor/grantee name-search approach:
this ties the result to the EXACT recorded document already captured
per-parcel from the assessor page (kern_real_batch_merged.csv's
recent_doc_number), so grantor/grantee here is provably tied to THIS
parcel, not just a name that exists somewhere in the county.

No CAPTCHA on this specific search form (confirmed live 2026-08-08).
"""
import csv
import sys
import time

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

SCRATCH = "/tmp/claude-1000/-home-chuck/e8fa5be3-9aea-4fd1-9c7a-07ad25a9bdf2/scratchpad"
BATCH = f"{SCRATCH}/kern_real_batch_merged.csv"
OUT = f"{SCRATCH}/kern_docnum_recorder_results.csv"


def fetch_doc(page, doc_number: str) -> dict | None:
    page.goto("https://recorderonline.co.kern.ca.us/cgi-bin/Osearchn.mbr/input", timeout=20000)
    page.wait_for_timeout(600)
    page.fill("input[name=Cert_From]", doc_number)
    page.click("input[name=B1]")
    page.wait_for_timeout(1800)
    text = page.inner_text("body")

    if doc_number not in text:
        return None

    import re
    # Row shape: DOCNUM  DATE  PAGES  TYPE  GRANTOR (R) \n GRANTEE (E)  ImageAvail
    m = re.search(
        re.escape(doc_number) + r"\s+(\d{2}/\d{2}/\d{4})\s+(\d+)\s+([A-Za-z' -]+?)\s*\n?\s*"
        r"([A-Z0-9 &'.,-]+?)\s*\(R\)\s*\n?\s*([A-Z0-9 &'.,-]+?)\s*\(E\)",
        text,
    )
    if not m:
        return {"doc_date": None, "pages": None, "doc_type": None, "grantor": None, "grantee": None, "raw_found": True}

    return {
        "doc_date": m.group(1),
        "pages": m.group(2),
        "doc_type": m.group(3).strip(),
        "grantor": m.group(4).strip(),
        "grantee": m.group(5).strip(),
        "raw_found": True,
    }


def main(limit=None):
    with open(BATCH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    active = [r for r in rows if r["likely_already_transferred"] != "True" and r.get("recent_doc_number")]
    if limit:
        active = active[:limit]

    results = []
    RECYCLE_EVERY = 25

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for i, row in enumerate(active):
            if i > 0 and i % RECYCLE_EVERY == 0:
                page.close()
                page = browser.new_page()

            apn = row["apn"]
            doc_number = row["recent_doc_number"]
            print(f"[{i+1}/{len(active)}] APN={apn} doc={doc_number} ...", end=" ")

            doc = None
            for attempt in range(2):
                try:
                    doc = fetch_doc(page, doc_number)
                except Exception as e:
                    print(f"[error: {e}] ", end="")
                    try:
                        page.close()
                    except Exception:
                        pass
                    page = browser.new_page()
                    doc = None
                if doc:
                    break

            if not doc:
                print("no result")
                results.append({
                    "apn": apn, "recent_doc_number": doc_number,
                    "candidate_name_from_list": row.get("owner_from_source_list"),
                    "doc_date": None, "pages": None, "doc_type": None,
                    "grantor": None, "grantee": None,
                })
                continue

            print(f"{doc['doc_type']} {doc['doc_date']} — Grantor: {doc['grantor']} / Grantee: {doc['grantee']}")
            results.append({
                "apn": apn,
                "recent_doc_number": doc_number,
                "candidate_name_from_list": row.get("owner_from_source_list"),
                "doc_date": doc["doc_date"],
                "pages": doc["pages"],
                "doc_type": doc["doc_type"],
                "grantor": doc["grantor"],
                "grantee": doc["grantee"],
            })
            time.sleep(0.3)

        browser.close()

    if results:
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)

    found = sum(1 for r in results if r.get("grantee"))
    print(f"\nDone. {found} of {len(results)} parcels got real grantor/grantee data tied to their exact recorded document.")
    print(f"Saved to {OUT}")


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit=lim)
