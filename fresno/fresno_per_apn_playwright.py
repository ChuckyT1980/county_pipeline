"""
Fresno County per-APN scraper via Playwright (real browser).

Why Playwright: the county's public pages (fresnocountyca.gov + kerncounty.com)
are protected by Akamai edge WAF that blocks curl/requests-based scraping with
403 Access Denied, regardless of User-Agent. A real Chromium browser presents
the correct TLS fingerprint, JS execution, and cookie handling to pass.

100% public source: uses only county-published web pages, no paid APIs, no auth
required (though CAPTCHA may appear on first hit — user solves once, session
carries via persistent context).

Usage:
    # First time (opens visible browser, user solves any CAPTCHA once):
    python fresno_per_apn_playwright.py --setup

    # Then scrape (uses saved session):
    python fresno_per_apn_playwright.py --apns 010-120-001,010-120-002
    python fresno_per_apn_playwright.py --from-csv fresno_auction_apns.csv

Outputs: fresno/fresno_per_apn_enriched.csv
"""
import argparse
import asyncio
import csv
import json
import os
import sys
from pathlib import Path

# playwright is imported lazily so this file is inspectable before install completes
FRESNO_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(FRESNO_DIR, ".playwright_session")
OUTPUT_CSV = os.path.join(FRESNO_DIR, "fresno_per_apn_enriched.csv")

# Fresno County assessor property search page (Akamai-protected — requires real browser)
FRESNO_ASSESSOR_SEARCH = (
    "https://www.fresnocountyca.gov/Departments/Assessor/Assessor-Property-Search"
)

# TODO: identify the exact per-APN URL pattern by navigating manually first.
# Common patterns for CA counties:
#   /Assessor/lookup?apn=010-120-001
#   /property/search?apn=010120001
# The --setup mode will let you navigate to a real parcel and record the URL.


async def setup_session():
    """Open visible browser so user can navigate + solve any CAPTCHA once.
    Session cookies save to SESSION_DIR for reuse by scrape mode.
    """
    from playwright.async_api import async_playwright

    Path(SESSION_DIR).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(FRESNO_ASSESSOR_SEARCH)
        print("Browser opened. Steps to complete manually:")
        print("  1. Solve any CAPTCHA / cookie banner")
        print("  2. Navigate to a specific parcel search (any real APN)")
        print("  3. Note the URL pattern that renders parcel details")
        print("  4. Close the browser when done")
        print()
        print("Session state (cookies) will be saved to:")
        print(f"  {SESSION_DIR}")
        print()
        input("Press Enter after closing the browser to continue... ")
        await ctx.close()


async def scrape_apn(apn: str) -> dict | None:
    """Scrape a single APN's public assessor data.

    NOTE: URL pattern must be discovered via --setup mode first.
    Fill in FRESNO_APN_URL_TEMPLATE below once known.
    """
    FRESNO_APN_URL_TEMPLATE = None  # e.g. "https://www.fresnocountyca.gov/lookup?apn={apn}"

    if FRESNO_APN_URL_TEMPLATE is None:
        print(f"ERROR: URL template not set yet. Run --setup first to discover it.")
        return None

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=True,
        )
        page = await ctx.new_page()
        try:
            url = FRESNO_APN_URL_TEMPLATE.format(apn=apn)
            resp = await page.goto(url, timeout=30_000)
            if resp and resp.status == 200:
                # TODO: parse the actual page structure once known
                html = await page.content()
                return {
                    "apn": apn,
                    "url": url,
                    "raw_html_len": len(html),
                    # Add: owner, situs, mailing, values once selectors known
                }
            return {"apn": apn, "url": url, "status": resp.status if resp else "no_resp"}
        finally:
            await ctx.close()


async def scrape_batch(apns: list[str]):
    results = []
    for i, apn in enumerate(apns, 1):
        print(f"  [{i}/{len(apns)}] APN {apn}...")
        r = await scrape_apn(apn)
        if r:
            results.append(r)
        await asyncio.sleep(1.5)  # polite delay between requests
    if not results:
        return
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nSaved {len(results)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--setup", action="store_true",
                   help="One-time browser session setup (visible browser, solve CAPTCHA).")
    p.add_argument("--apns", type=str,
                   help="Comma-separated APN list to scrape.")
    p.add_argument("--from-csv", type=str,
                   help="Path to CSV with 'APN' column to scrape all rows from.")
    args = p.parse_args()

    if args.setup:
        asyncio.run(setup_session())
    elif args.apns:
        asyncio.run(scrape_batch([a.strip() for a in args.apns.split(",")]))
    elif args.from_csv:
        with open(args.from_csv, encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            apns = [r["APN"] for r in reader if r.get("APN")]
        asyncio.run(scrape_batch(apns))
    else:
        p.print_help()
