"""
Universal Playwright-based scraper for any CA county web endpoint.

Works on Akamai-gated / JS-heavy / CAPTCHA-protected sites that block curl.
User solves any CAPTCHA once on first run; session cookies persist for later runs.

Currently wraps:
  - Kern County Assessor / Tax Collector (kcttc.co.kern.ca.us — CAPTCHA)
  - Kern County Property (kerncounty.com — Akamai)

Add new counties by defining an entry in COUNTY_SCRAPERS below.

Usage:
    # First-time setup (opens visible browser, solve CAPTCHA if any):
    python universal_playwright_scraper.py --county kern --setup

    # After setup, batch scrape:
    python universal_playwright_scraper.py --county kern --from-csv kern/kern_apn_seed.csv --limit 100
"""
import argparse
import asyncio
import csv
import re
from pathlib import Path

ROOT = Path(__file__).parent
SESSION_DIR = ROOT / ".playwright_sessions"


COUNTY_SCRAPERS = {
    "kern": {
        "search_url": "https://www.kcttc.co.kern.ca.us/Payment/mainsearch.aspx",
        "apn_input_selector": "input[name*='APN'], input[id*='APN'], input[name*='parcel']",
        "submit_selector": "input[type=submit], button[type=submit]",
        "result_owner_selector": "*",  # will use regex against page text
        "owner_pattern": r"(?:Owner|Assessee)[^:]*:\s*([A-Z][A-Z\s,&\.]{5,80})",
        "situs_pattern": r"(?:Situs|Property Address|Location)[^:]*:\s*([\d][^\n<]{5,120})",
        "value_pattern": r"(?:Assessed Value|Total Value)[^\$]*\$([\d,]+)",
    },
}


async def setup_session(county: str):
    """Open visible browser once. User completes any CAPTCHA, closes browser."""
    from playwright.async_api import async_playwright

    cfg = COUNTY_SCRAPERS[county]
    sess = SESSION_DIR / county
    sess.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(sess),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        print(f"Navigating to {cfg['search_url']}")
        await page.goto(cfg["search_url"])
        print("Complete these steps in the browser:")
        print("  1. Solve any CAPTCHA (if present)")
        print("  2. Do one manual search (any real APN) to establish session cookies")
        print("  3. Close the browser when done")
        input("Press Enter after closing the browser... ")
        await ctx.close()
        print(f"Session saved to {sess}")


async def scrape_apn(page, apn: str, cfg: dict) -> dict:
    """Search for one APN, extract owner/situs/values from result page."""
    apn_clean = re.sub(r"[^0-9\-]", "", apn)
    try:
        await page.goto(cfg["search_url"], timeout=20000, wait_until="networkidle")

        # Find the APN input
        input_locator = page.locator(cfg["apn_input_selector"]).first
        try:
            await input_locator.wait_for(timeout=5000)
            await input_locator.fill(apn_clean)
        except Exception:
            return {"apn": apn, "status": "input_not_found"}

        # Submit
        submit = page.locator(cfg["submit_selector"]).first
        await submit.click()
        await page.wait_for_load_state("networkidle", timeout=20000)

        # Extract via regex on page text
        text = await page.evaluate("() => document.body.innerText")

        def _grab(pat):
            m = re.search(pat, text)
            return m.group(1).strip() if m else ""

        return {
            "apn": apn,
            "status": "ok",
            "owner": _grab(cfg["owner_pattern"]),
            "situs": _grab(cfg["situs_pattern"]),
            "assessed_value": _grab(cfg["value_pattern"]),
            "raw_text_len": len(text),
        }
    except Exception as e:
        return {"apn": apn, "status": f"err_{str(e)[:40]}"}


async def scrape_batch(county: str, apns: list, delay: float = 1.5):
    from playwright.async_api import async_playwright

    cfg = COUNTY_SCRAPERS[county]
    sess = SESSION_DIR / county
    if not sess.exists():
        print(f"ERROR: no session found at {sess}. Run --setup first.")
        return

    out_dir = ROOT / "data" / county
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{county}_playwright_results.csv"

    print(f"Scraping {len(apns)} {county} APNs via Playwright (uses saved session)...")
    results = []

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(sess),
            headless=True,
        )
        page = await ctx.new_page()

        for i, apn in enumerate(apns, 1):
            r = await scrape_apn(page, apn, cfg)
            results.append(r)
            status = r.get("status", "?")
            owner = r.get("owner", "")[:40] or "(no owner)"
            print(f"  [{i:4}/{len(apns)}] {apn}  {status}  {owner}")
            await asyncio.sleep(delay)

        await ctx.close()

    if results:
        keys = []
        for r in results:
            for k in r.keys():
                if k not in keys: keys.append(k)
        with open(out_path, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=keys)
            w.writeheader()
            w.writerows(results)
        print(f"\nSaved {len(results)} rows to {out_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--county", required=True, choices=list(COUNTY_SCRAPERS.keys()))
    p.add_argument("--setup", action="store_true", help="One-time browser session setup")
    p.add_argument("--from-csv", help="CSV file with APN column")
    p.add_argument("--apns", help="Comma-separated APN list")
    p.add_argument("--limit", type=int)
    p.add_argument("--delay", type=float, default=1.5)
    args = p.parse_args()

    if args.setup:
        asyncio.run(setup_session(args.county))
        return

    apns = []
    if args.apns:
        apns = [a.strip() for a in args.apns.split(",") if a.strip()]
    elif args.from_csv:
        with open(args.from_csv, encoding="utf-8") as fp:
            for r in csv.DictReader(fp):
                a = (r.get("parcel_number") or r.get("APN") or r.get("apn") or "").strip()
                if a: apns.append(a)
    if args.limit:
        apns = apns[:args.limit]
    if not apns:
        print("ERROR: no APNs. Use --apns or --from-csv or --setup.")
        return

    asyncio.run(scrape_batch(args.county, apns, delay=args.delay))


if __name__ == "__main__":
    main()
