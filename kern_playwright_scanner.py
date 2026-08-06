"""
Kern County Playwright-based scanner — reliable per-APN scraping via real browser.

Reuses the search flow that Playwright already proved works (index.aspx with
ddlSearchType=apn + txtSearchText). Extracts owner + situs + values from the
results table.

Speed: ~2-3 seconds per parcel via headless Chromium.
50 parcels = ~2 min.  500 = ~20 min.  All 1,079 FATCO seed = ~40 min.

Usage:
    python kern_playwright_scanner.py --from-csv kern/kern_apn_sample_50.csv
"""
import argparse
import asyncio
import csv
import re
import time
from pathlib import Path

ROOT = Path(__file__).parent
SEARCH_URL = "https://assessorapps.kerncounty.com/PropertySearch/Parcels/index.aspx"


async def search_one(page, apn: str) -> dict:
    """Perform one APN search on Kern's PropertySearch page + parse result."""
    apn_clean = re.sub(r"[^0-9\-]", "", apn)
    if not apn_clean:
        return {"apn": apn, "status": "invalid"}

    try:
        await page.goto(SEARCH_URL, timeout=25000, wait_until="domcontentloaded")
        await page.select_option("select[name='ddlSearchType']", "apn")
        await page.fill("input[name='txtSearchText']", apn_clean)

        # Click Search — try multiple selectors to be robust
        for sel in ["input[value='Search']", "button:has-text('Search')",
                    "[id*='btnSearch'] input", "[id*='btnSearch']"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    break
            except Exception:
                pass
        else:
            await page.press("input[name='txtSearchText']", "Enter")

        await page.wait_for_load_state("networkidle", timeout=15000)
        text = await page.evaluate("() => document.body.innerText")

        if "No records to display" in text:
            return {"apn": apn, "status": "no_records"}

        # Extract owner + situs + values from results table
        # Real result page has: ATN/APN | File Number | Address | City
        # And clicking a row opens details. For MVP: just extract what's in the summary row.
        rows_text = await page.evaluate("""() => {
            const rows = document.querySelectorAll('tr');
            return Array.from(rows).map(r => r.innerText).join('|||ROW|||');
        }""")

        # Find the data row (has an APN in it)
        data_row = ""
        for row in rows_text.split("|||ROW|||"):
            if apn_clean in row.replace("-", "") or apn in row:
                data_row = row.strip()
                break

        # Try clicking through to detail page
        detail = {}
        try:
            link = page.locator(f"a:has-text('{apn}')").first
            if await link.count() > 0:
                await link.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
                detail_text = await page.evaluate("() => document.body.innerText")

                def _grab(pat, default=""):
                    m = re.search(pat, detail_text, re.I)
                    return m.group(1).strip() if m else default

                detail = {
                    "owner": _grab(r"(?:Owner Name|Assessee)[^:]*:?\s*([A-Z][A-Z0-9\s&,'\.\-\/]{4,80})"),
                    "situs": _grab(r"(?:Situs Address|Property Location)[^:]*:?\s*([\d][^\n]{5,120})"),
                    "mailing": _grab(r"(?:Mailing Address)[^:]*:?\s*([^\n]{10,120})"),
                    "assessed_value": _grab(r"(?:Total Value|Assessed Value)[^\$]*\$([\d,]+)"),
                }
        except Exception:
            pass

        return {
            "apn": apn,
            "status": "ok" if data_row or detail else "no_data",
            "summary_row": data_row[:200],
            **detail,
        }

    except Exception as e:
        return {"apn": apn, "status": f"err_{str(e)[:40]}"}


async def scan_batch(apns: list, delay: float = 1.0):
    from playwright.async_api import async_playwright

    out_dir = ROOT / "data" / "kern"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "kern_playwright_results.csv"

    print(f"Scanning {len(apns)} Kern APNs via Playwright...")
    results = []
    t0 = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
        )
        page = await ctx.new_page()

        for i, apn in enumerate(apns, 1):
            r = await search_one(page, apn)
            results.append(r)
            elapsed = time.time() - t0
            rate = i / elapsed
            print(f"  [{i:3}/{len(apns)}] {apn:20} status={r.get('status'):15} {'owner=' + str(r.get('owner',''))[:40] if r.get('owner') else ''}")
            await asyncio.sleep(delay)

        await browser.close()

    elapsed = time.time() - t0
    print(f"\nComplete in {elapsed:.1f}s ({elapsed/len(apns):.1f}s per parcel)")

    if results:
        keys = []
        for r in results:
            for k in r.keys():
                if k not in keys: keys.append(k)
        with open(out_path, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=keys)
            w.writeheader()
            w.writerows(results)
        print(f"Saved to {out_path}")

    oks = sum(1 for r in results if r.get("status") == "ok")
    no_recs = sum(1 for r in results if r.get("status") == "no_records")
    print(f"\nSummary: {oks} with data, {no_recs} no_records, {len(results)-oks-no_recs} other")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--from-csv")
    p.add_argument("--apns")
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args()

    apns = []
    if args.apns:
        apns = [a.strip() for a in args.apns.split(",") if a.strip()]
    elif args.from_csv:
        with open(args.from_csv, encoding="utf-8") as fp:
            for r in csv.DictReader(fp):
                a = (r.get("parcel_number") or r.get("APN") or "").strip()
                if a: apns.append(a)
    if args.limit:
        apns = apns[:args.limit]
    if not apns:
        print("ERROR: no APNs")
    else:
        asyncio.run(scan_batch(apns))
