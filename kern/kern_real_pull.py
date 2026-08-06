"""
Real Kern assessor pull — free, stealth-browser + local OCR CAPTCHA solve.
Verified-or-excluded, no fake formulas. Replaces the 5x-min-bid estimate
with the actual net taxable value from assessorapps.kerncounty.com.
"""
import csv
import re
import subprocess
import time

from PIL import Image, ImageFilter
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

TESS = "/tmp/claude-1000/-home-chuck/e8fa5be3-9aea-4fd1-9c7a-07ad25a9bdf2/scratchpad/localdeps/extracted/usr/bin/tesseract"
SRC = "/mnt/c/Users/chuck/Downloads/county_pipeline/kern/kern_REAL_AUCTION_PARCELS_CLEAN.csv"
OUT = "/tmp/claude-1000/-home-chuck/e8fa5be3-9aea-4fd1-9c7a-07ad25a9bdf2/scratchpad/kern_real_batch.csv"


def solve_captcha(img_path: str, proc_path: str) -> str:
    img = Image.open(img_path).convert("L")
    big = img.resize((img.width * 5, img.height * 5), Image.LANCZOS)
    big = big.filter(ImageFilter.MedianFilter(3))
    bw = big.point(lambda p: 255 if p > 150 else 0)
    bw.save(proc_path)
    out = subprocess.run(
        [TESS, proc_path, "stdout", "--psm", "8",
         "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"],
        capture_output=True, text=True,
    )
    return re.sub(r"[^A-Z0-9]", "", out.stdout.strip().upper())


def to_search_apn(raw_apn: str) -> str:
    """Kern's search wants the book-page-parcel prefix (8-9 digits worth)."""
    digits_and_dashes = raw_apn.strip()
    parts = digits_and_dashes.split("-")
    if len(parts) >= 3:
        return f"{parts[0]}-{parts[1]}-{parts[2]}"
    return digits_and_dashes


def parse_detail_page(text: str) -> dict:
    out = {"situs": None, "net_taxable_value": None, "status": None,
           "recent_doc_number": None, "recent_doc_type": None, "recent_doc_date": None,
           "all_doc_types": []}

    m = re.search(r"Status\s+(\S+)", text)
    if m:
        out["status"] = m.group(1)

    m = re.search(r"Site Addr\.\s+([^\n]+)", text)
    if m:
        out["situs"] = m.group(1).strip()

    m = re.search(r"Net Total Taxable Value\s+\$([\d,]+)", text)
    if m:
        out["net_taxable_value"] = float(m.group(1).replace(",", ""))

    idx = text.find("Recorded Documents")
    section = text[idx:idx + 2000] if idx >= 0 else ""
    # Capture every row in the table, tightly bounded to the actual columns
    # (doc number \t doc type \t date), not a greedy scan across the whole page.
    docs = re.findall(r"(\d{6,})\t\xa0([^\t\n]{1,60}?)\t\xa0(\d{2}/\d{2}/\d{4})", section)
    if docs:
        # Most recent by recorded date, not just first row in the table.
        from datetime import datetime
        docs_parsed = [(n, t.strip(), d, datetime.strptime(d, "%m/%d/%Y")) for n, t, d in docs]
        docs_parsed.sort(key=lambda x: x[3], reverse=True)
        out["recent_doc_number"] = docs_parsed[0][0]
        out["recent_doc_type"] = docs_parsed[0][1]
        out["recent_doc_date"] = docs_parsed[0][2]
        out["all_doc_types"] = [d[1] for d in docs_parsed]

    return out


def fetch_one(page, apn_search: str, max_captcha_tries: int = 8) -> dict | None:
    page.goto("https://assessorapps.kerncounty.com/PropertySearch/Parcels/index.aspx", timeout=30000)
    page.wait_for_timeout(1200)
    page.select_option("#ddlSearchType", value="apn")
    page.fill("#txtSearchText", apn_search)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2000)

    tries = 0
    while "CAPTCHA" in page.url and tries < max_captcha_tries:
        tries += 1
        el = page.query_selector("img")
        if not el:
            break
        img_path = "/tmp/kern_live_captcha.png"
        proc_path = "/tmp/kern_live_captcha_proc.png"
        el.screenshot(path=img_path)
        answer = solve_captcha(img_path, proc_path)
        inputs = page.eval_on_selector_all("input[type=text]", "els => els.map(e => e.id)")
        if not inputs:
            break
        page.fill("#" + inputs[0], answer)
        page.click("input[type=submit], button")
        page.wait_for_timeout(2000)
        if "CAPTCHA" not in page.url:
            break
        try:
            page.click("text=Generate New Image", timeout=2000)
            page.wait_for_timeout(800)
        except Exception:
            pass

    if "CAPTCHA" in page.url:
        return None  # genuinely failed after max retries, exclude, don't guess

    # The Recorded Documents section loads via a separate async call after the
    # main page renders — wait for the network to actually go idle, and confirm
    # the "Recorded Documents" heading itself is present, instead of guessing
    # a fixed delay. This is what was causing inconsistent results.
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    try:
        page.wait_for_selector("text=Recorded Documents", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(500)

    text = page.inner_text("body")
    if "No Records Found" in text or "not found" in text.lower():
        return None

    parsed = parse_detail_page(text)
    if parsed["net_taxable_value"] is None:
        return None  # no real value found, excluded, not defaulted to anything

    return parsed


def main(limit: int = 25):
    with open(SRC, encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))
    candidates = rows[:limit]

    results = []
    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for i, row in enumerate(candidates):
            raw_apn = row.get("Parcel_Number") or row.get("APN_1") or ""
            apn_search = to_search_apn(raw_apn)
            print(f"[{i+1}/{len(candidates)}] {raw_apn} (search: {apn_search}) ...", end=" ")
            parsed = None
            for page_attempt in range(2):  # retry once on a page-load timing miss
                try:
                    parsed = fetch_one(page, apn_search)
                except Exception as e:
                    print(f"ERROR: {e}")
                    parsed = None
                if parsed:
                    break

            if not parsed:
                print("excluded (no verified value / CAPTCHA failed / not found)")
                continue

            record = {
                "apn": raw_apn,
                "owner_from_source_list": row.get("Owner"),
                "situs": parsed["situs"],
                "net_taxable_value": parsed["net_taxable_value"],
                "status": parsed["status"],
                "recent_doc_number": parsed["recent_doc_number"],
                "recent_doc_type": parsed["recent_doc_type"],
                "recent_doc_date": parsed["recent_doc_date"],
                "likely_already_transferred": bool(parsed["recent_doc_type"] and "tax" in parsed["recent_doc_type"].lower()),
            }
            results.append(record)
            flag = " [POSSIBLE PRIOR TAX DEED - VERIFY]" if record["likely_already_transferred"] else ""
            print(f"REAL: NTV ${parsed['net_taxable_value']:,.0f}{flag}")
            time.sleep(0.5)

        browser.close()

    if results:
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)

    print(f"\nDone. {len(results)} verified real records out of {len(candidates)} attempted.")
    print(f"Saved to {OUT}")


if __name__ == "__main__":
    main(limit=140)
