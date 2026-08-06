"""
Fresno County auction-result PDF fetcher + parser.

Fetches the two known excess-proceeds result PDFs from fresnocountyca.gov
(Akamai-protected — requires a real Chromium via Playwright), parses each
with pdfplumber, and writes a combined CSV of real sale data:

    fresno/fresno_historical_sales.csv

Columns:
    source_pdf      filename the row came from
    auction_date    parsed from PDF text or filename (YYYY-MM-DD)
    item_no         sequential item number in that auction
    apn             normalized 8-digit form (joins FC_PARCEL_SELECT)
    apn_5part       dashed 5-part form (XXX-XXX-XX-000-0) for readability
    sales_price     winning bid (float)
    excess_proceeds float
    min_bid         derived = sales_price - excess_proceeds

Integrity rules:
    - Only rows that parse cleanly are emitted. Rows that fail parsing are
      logged and skipped — never guessed.
    - PDFs are fetched fresh via Playwright with a persistent session so any
      Akamai cookie/CAPTCHA handshake is solved once and reused.

Usage:
    python fresno_fetch_and_parse_results.py
    python fresno_fetch_and_parse_results.py --skip-download   # parse only
"""
import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import pdfplumber

FRESNO_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(FRESNO_DIR, ".playwright_session")
DOWNLOAD_DIR = os.path.join(FRESNO_DIR, "downloaded_pdfs")
OUTPUT_CSV = os.path.join(FRESNO_DIR, "fresno_historical_sales.csv")

PDF_SOURCES = [
    {
        "url": (
            "https://www.fresnocountyca.gov/files/assets/county/v/1/auditor-controller-"
            "treasurer-tax-collector/forms/list-of-sales-and-excess-proceeds.pdf"
        ),
        "filename": "list-of-sales-and-excess-proceeds.pdf",
        "auction_date_fallback": None,
    },
    {
        "url": (
            "https://www.fresnocountyca.gov/files/assets/county/v/2/auditor-controller-"
            "treasurer-tax-collector/tax-sale-amp-excess-proceeds/"
            "march-27-28-april-4-2025-excess-proceed-list.pdf"
        ),
        "filename": "march-27-28-april-4-2025-excess-proceed-list.pdf",
        "auction_date_fallback": "2025-04-04",
    },
]

# Sample line format (from handoff):
#   ITEM  SALES  EXCESS
#   NO.   APN    PRICE  PROCEEDS
#   13  090-101-15  3,500.00  1,231.97
APN_RE = re.compile(r"\d{3}-\d{3}-\d{2}")
AMOUNT_RE = re.compile(r"[\d,]+\.\d{2}")


def normalize_apn(apn_dashed: str) -> str:
    """XXX-XXX-XX -> 8-digit zero-padded form that joins FC_PARCEL_SELECT."""
    digits = re.sub(r"\D", "", apn_dashed)
    return digits.zfill(8)


def apn_5part(apn_dashed: str) -> str:
    """XXX-XXX-XX -> XXX-XXX-XX-000-0 (readable 5-part form)."""
    digits = re.sub(r"\D", "", apn_dashed).zfill(8)
    return f"{digits[0:3]}-{digits[3:6]}-{digits[6:8]}-000-0"


def extract_auction_date_from_text(text: str) -> str | None:
    """Try to find a sale date in the PDF text. Returns YYYY-MM-DD or None.

    Handles formats like:
      "MARCH 11-14, 2022"            -> 2022-03-14 (last sale day)
      "March 27-28, & April 4, 2025" -> 2025-04-04 (last sale day)
      "3/28/2025" / "2025-03-28"
    """
    from datetime import datetime

    # 1) Month name with optional day range, e.g. "MARCH 11-14, 2022".
    #    Captures the LAST day of the range.
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)"
        r"\s+\d{1,2}\s*-\s*(\d{1,2})\s*,?\s*(20\d{2})",
        text, re.IGNORECASE,
    )
    if m:
        month, day, year = m.group(1), m.group(2), m.group(3)
        try:
            return datetime.strptime(f"{month} {day}, {year}", "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 2) Bare month + day + year, e.g. "March 27, 2025".
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)"
        r"\s+(\d{1,2})\s*,?\s*(20\d{2})",
        text, re.IGNORECASE,
    )
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}, {m.group(3)}", "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 3) Numeric formats.
    for pat in (r"\d{1,2}/\d{1,2}/20\d{2}", r"\d{4}-\d{2}-\d{2}"):
        m = re.search(pat, text)
        if m:
            date_str = m.group(0)
            for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
    return None


def parse_pdf(pdf_path: str, source_pdf: str, auction_date_fallback: str | None) -> list[dict]:
    """Parse a results PDF into rows. Never invents values for bad rows."""
    rows = []
    parse_failures = []

    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    auction_date = extract_auction_date_from_text(full_text) or auction_date_fallback or ""

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]
        apn_match = APN_RE.search(line)
        if not apn_match:
            i += 1
            continue

        apn_dashed = apn_match.group(0)
        remainder = line[apn_match.end():].strip()
        amounts = AMOUNT_RE.findall(remainder)

        # Single-line rows:  "13  090-101-15  3,500.00  1,231.97"
        # Multi-line rows:   "13  090-101-15" then "3,500.00  1,231.97" on next line(s)
        if len(amounts) >= 2:
            sales_price = amounts[0]
            excess = amounts[1]
            item_no_match = re.match(r"(\d+)", line[:apn_match.start()].strip())
            item_no = item_no_match.group(1) if item_no_match else ""
            _emit_row(rows, parse_failures, source_pdf, auction_date, item_no,
                      apn_dashed, sales_price, excess, line)
            i += 1
            continue

        # Try to find the amounts on following lines (before next APN).
        collected = list(amounts)
        j = i + 1
        while j < len(lines) and len(collected) < 2 and not APN_RE.search(lines[j]):
            candidate = lines[j]
            if AMOUNT_RE.search(candidate):
                collected.extend(AMOUNT_RE.findall(candidate))
            j += 1

        if len(collected) >= 2:
            item_no_match = re.match(r"(\d+)", line[:apn_match.start()].strip())
            item_no = item_no_match.group(1) if item_no_match else ""
            _emit_row(rows, parse_failures, source_pdf, auction_date, item_no,
                      apn_dashed, collected[0], collected[1], line + " | " + " ".join(lines[i+1:j]))
        else:
            parse_failures.append((line, "could not find both price and excess amounts"))
        i = j

    if parse_failures:
        print(f"  [{source_pdf}] {len(parse_failures)} unparsed row(s) skipped:")
        for l, why in parse_failures[:10]:
            print(f"    SKIP ({why}): {l[:100]}")
        if len(parse_failures) > 10:
            print(f"    ... and {len(parse_failures) - 10} more")

    return rows


def _emit_row(rows, failures, source_pdf, auction_date, item_no, apn_dashed,
              sales_price_str, excess_str, context_line):
    try:
        sales_price = float(sales_price_str.replace(",", ""))
        excess = float(excess_str.replace(",", ""))
        min_bid = round(sales_price - excess, 2)
        if sales_price <= 0 or excess < 0:
            failures.append((context_line, "non-positive price"))
            return
        rows.append({
            "source_pdf": source_pdf,
            "auction_date": auction_date,
            "item_no": item_no,
            "apn": normalize_apn(apn_dashed),
            "apn_5part": apn_5part(apn_dashed),
            "sales_price": sales_price,
            "excess_proceeds": excess,
            "min_bid": min_bid,
        })
    except (ValueError, TypeError) as e:
        failures.append((context_line, f"bad amount: {e}"))


def _download_requests(pdf_spec: dict, target: str) -> bool:
    """Fast path: plain HTTP download. Works when Akamai isn't challenging
    (verified 2026-07-31 on both URLs). Returns True on success."""
    import requests
    try:
        r = requests.get(pdf_spec["url"], timeout=60)
        if r.status_code == 200 and r.content.startswith(b"%PDF"):
            with open(target, "wb") as f:
                f.write(r.content)
            print(f"  OK   {pdf_spec['filename']} (requests, {len(r.content):,} bytes)")
            return True
        print(f"  FAIL {pdf_spec['filename']}: requests got HTTP {r.status_code}, not PDF")
        return False
    except Exception as e:
        print(f"  FAIL {pdf_spec['filename']}: requests {type(e).__name__}: {e}")
        return False


async def download_pdf(page, pdf_spec: dict) -> bool:
    """Download one PDF into DOWNLOAD_DIR using the Playwright page.
    Returns True on success."""
    import urllib.parse

    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    target = os.path.join(DOWNLOAD_DIR, pdf_spec["filename"])

    filename = pdf_spec["filename"]
    url = pdf_spec["url"]

    # Navigate the browser to the PDF URL; Chromium either embeds it or prompts
    # a download. We also grab via request within the page context as fallback.
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if resp is None or resp.status != 200:
            print(f"  FAIL {filename}: HTTP {resp.status if resp else 'no response'}")
            return False

        body = await resp.body()
        if body.startswith(b"%PDF"):
            with open(target, "wb") as f:
                f.write(body)
            print(f"  OK   {filename} ({len(body):,} bytes)")
            return True

        # Some server configs stream HTML wrapper instead — fall back to a
        # context-API fetch inside the browser.
        js_result = await page.evaluate(
            """
            async (url) => {
                const r = await fetch(url);
                const buf = await r.arrayBuffer();
                return { status: r.status, b64: await _b64(buf) };
            }
            """.replace("_b64", "(_b)=>btoa(String.fromCharCode.apply(null,new Uint8Array(_b)))")
        )
        import base64
        data = base64.b64decode(js_result["b64"])
        if data.startswith(b"%PDF"):
            with open(target, "wb") as f:
                f.write(data)
            print(f"  OK   {filename} (via fetch, {len(data):,} bytes)")
            return True
        else:
            print(f"  FAIL {filename}: response not a PDF (status {js_result['status']}, {len(data)} bytes)")
            return False
    except Exception as e:
        print(f"  FAIL {filename}: {type(e).__name__}: {e}")
        return False


async def _fetch_all():
    from playwright.async_api import async_playwright

    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    results = {}

    # Fast path first: Akamai has not been challenging these URLs recently.
    requests_pending = []
    for spec in PDF_SOURCES:
        target = os.path.join(DOWNLOAD_DIR, spec["filename"])
        if os.path.exists(target) and os.path.getsize(target) > 0:
            results[spec["filename"]] = True
            print(f"  SKIP {spec['filename']}: already present")
            continue
        if _download_requests(spec, target):
            results[spec["filename"]] = True
        else:
            requests_pending.append(spec)

    if not requests_pending:
        return results

    print(f"\nRequests path blocked {len(requests_pending)} file(s) — switching to Playwright...")
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=True,
            viewport={"width": 1280, "height": 900},
            accept_downloads=True,
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        # Warm the domain so Akamai issues any challenge cookie to a fresh session.
        try:
            await page.goto("https://www.fresnocountyca.gov", wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"  WARN warm-up: {e}")
        for spec in requests_pending:
            results[spec["filename"]] = await download_pdf(page, spec)
        await ctx.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch + parse Fresno excess-proceeds PDFs.")
    parser.add_argument("--skip-download", action="store_true",
                        help="Only parse PDFs already in fresno/downloaded_pdfs/")
    args = parser.parse_args()

    if not args.skip_download:
        print("Downloading Fresno auction-result PDFs via Playwright...")
        results = asyncio.run(_fetch_all())
        missing = [f for f, ok in results.items() if not ok]
        if missing:
            print(f"WARNING: download failed for: {missing}")
    else:
        print("Skipping download (--skip-download).")

    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    all_rows = []
    for spec in PDF_SOURCES:
        pdf_path = os.path.join(DOWNLOAD_DIR, spec["filename"])
        if not os.path.exists(pdf_path):
            print(f"SKIP {spec['filename']}: not present in {DOWNLOAD_DIR}")
            continue
        print(f"Parsing {spec['filename']}...")
        all_rows.extend(parse_pdf(pdf_path, spec["filename"], spec["auction_date_fallback"]))

    if not all_rows:
        print("No rows parsed. Aborting — no output written.")
        sys.exit(1)

    import csv
    fieldnames = ["source_pdf", "auction_date", "item_no", "apn", "apn_5part",
                  "sales_price", "excess_proceeds", "min_bid"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    total_excess = sum(r["excess_proceeds"] for r in all_rows)
    print(f"\nWrote {len(all_rows)} rows to {OUTPUT_CSV}")
    print(f"Total excess proceeds: ${total_excess:,.2f}")


if __name__ == "__main__":
    main()
