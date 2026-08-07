"""
Real Fresno assessed-value pull against the official 2026 tax sale list
(fresno_official_2026_tax_sale_list.csv — sourced from Board of Supervisors
Resolution 26-245, File 26-0600, real item/default/APN/min-bid, not scraped).

Uses assrmaps.co.fresno.ca.us/binlookup/ParcelLookup.aspx (free, no CAPTCHA,
no proxy needed — confirmed live 2026-08-06). Owner name is NOT available
here (Fresno removed APN->owner lookup Jan 2025 per CA privacy law) — parked
as unverified, not guessed.
"""
import csv
import re
import time

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

SRC = "/mnt/c/Users/chuck/Downloads/county_pipeline/fresno/fresno_official_2026_tax_sale_list.csv"
OUT = "/mnt/c/Users/chuck/Downloads/county_pipeline/fresno/fresno_real_batch.csv"


def fetch_assessed_value(page, apn: str) -> dict | None:
    parts = apn.rstrip("S").split("-")
    if len(parts) != 3:
        return None
    book, pg, parcel = parts
    page.goto("https://assrmaps.co.fresno.ca.us/binlookup/ParcelLookup.aspx", timeout=30000)
    page.wait_for_timeout(800)
    page.fill("#txtBook", book)
    page.fill("#txtPage", pg)
    page.fill("#txtBlockParcel", parcel)
    page.click("#btnSearchAPN")
    page.wait_for_timeout(1800)
    text = page.inner_text("body")

    if "Incorrect" in text or "No Results" in text:
        return None

    def _grab(label):
        m = re.search(re.escape(label) + r"\s*\n*\s*\$?([\d,]+)", text)
        return float(m.group(1).replace(",", "")) if m else None

    total = _grab("Total:")
    land = _grab("Land:")
    imps = _grab("Imps/TFI:")
    if total is None:
        return None

    m = re.search(r"Location:\s*\n*\s*([^\n]+)", text)
    situs = m.group(1).strip() if m else None
    m2 = re.search(r"Effective Year:\s*\n*\s*(\d+)", text)
    eff_year = m2.group(1) if m2 else None

    return {
        "net_assessed_value": total,
        "land_value": land,
        "improvements_value": imps,
        "situs_confirmed": situs,
        "effective_year": eff_year,
    }


def main(limit: int = 40):
    with open(SRC, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[:limit]

    results = []
    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for i, row in enumerate(rows):
            apn = row["apn"]
            print(f"[{i+1}/{len(rows)}] {apn} ...", end=" ")
            try:
                val = fetch_assessed_value(page, apn)
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            if not val:
                print("excluded (no verified assessed value found)")
                continue

            record = {
                "item_number": row["item_number"],
                "default_case_number": row["default_case_number"],
                "apn": apn,
                "location_official": row["location"],
                "minimum_bid": row["minimum_bid"],
                **val,
            }
            results.append(record)
            print(f"REAL: assessed=${val['net_assessed_value']:,.0f}")
            time.sleep(0.4)

        browser.close()

    if results:
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)

    print(f"\nDone. {len(results)} verified real records out of {len(rows)} attempted.")
    print(f"Saved to {OUT}")


if __name__ == "__main__":
    main()
