"""
Kern County Assessor - Free Public Data Routes
California R&TC §408 requires public inspection of assessment roll.
Trying every legitimate free path:
1. Kern County Assessor direct property lookup (Playwright headless - real browser)
2. Kern County bulk assessment roll download page
3. California State Controller property tax data
4. Kern County Open Data / bulk data portal
5. California Board of Equalization assessor roll data
"""
import os, re, requests, json
import pandas as pd
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
BASE = r"C:\Users\chuck\Downloads\county_pipeline\kern"

print("=== [1] KERN ASSESSOR BULK DATA / OPEN DATA PORTAL ===")
urls = [
    "https://assessor.co.kern.ca.us/assessor/bulk-data",
    "https://assessor.co.kern.ca.us/assessor/open-data",
    "https://assessor.co.kern.ca.us/assessor/downloads",
    "https://assessor.co.kern.ca.us/assessor/assessment-roll",
    "https://assessor.co.kern.ca.us/assessor/public-records",
    "https://assessor.co.kern.ca.us/",
    "https://co.kern.ca.us/assessor/",
    "https://www.kerncounty.com/government/departments/assessor-recorder",
    "https://www.kerncounty.com/government/departments/assessor",
]
for url in urls:
    try:
        r = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.text.strip() if soup.title else "no title"
        print(f"  {url}")
        print(f"    -> {r.status_code} | {title[:70]}")
        if r.status_code == 200:
            # Look for bulk data / download links
            for l in soup.find_all("a", href=True):
                if any(k in l.text.lower() or k in l["href"].lower()
                       for k in ["download","bulk","roll","csv","excel","data","parcel","apn","search","lookup"]):
                    print(f"    LINK: {l.text.strip()[:60]} -> {l['href'][:80]}")
    except Exception as e:
        print(f"  {url} -> {e}")

print("\n=== [2] CALIFORNIA STATE CONTROLLER PROPERTY TAX DATA ===")
sco_urls = [
    "https://www.sco.ca.gov/ardtax_prop_tax_info.html",
    "https://www.sco.ca.gov/ardtax_county_data.html",
    "https://www.sco.ca.gov/ard_county_high_value.html",
]
for url in sco_urls:
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.text.strip() if soup.title else ""
        print(f"  {url} -> {r.status_code} | {title[:60]}")
        if r.status_code == 200:
            for l in soup.find_all("a", href=True):
                if any(k in l.text.lower() or k in l["href"].lower()
                       for k in ["kern","parcel","roll","download","csv","excel","data"]):
                    print(f"    LINK: {l.text.strip()[:60]} -> {l['href'][:80]}")
    except Exception as e:
        print(f"  {url} -> {e}")

print("\n=== [3] KERN COUNTY ASSESSOR VIA PLAYWRIGHT (REAL BROWSER) ===")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("  Playwright browser launched.")

        # Hit the assessor search page
        page.goto("https://assessor.co.kern.ca.us/", timeout=15000)
        print(f"  Assessor home: {page.title()}")
        print(f"  URL: {page.url}")

        # Get all links
        links = page.eval_on_selector_all("a[href]", "els => els.map(e => ({text: e.innerText, href: e.href}))")
        for l in links:
            if any(k in l.get("text","").lower() or k in l.get("href","").lower()
                   for k in ["search","parcel","apn","property","lookup","roll"]):
                print(f"  LINK: {l.get('text','')[:50]} -> {l.get('href','')[:80]}")

        browser.close()
except ImportError:
    print("  Playwright not installed. Installing...")
    import subprocess
    subprocess.run(["pip", "install", "playwright"], capture_output=True)
    subprocess.run(["python", "-m", "playwright", "install", "chromium"], capture_output=True)
    print("  Run script again after install.")
except Exception as e:
    print(f"  Playwright error: {e}")

print("\n=== [4] KERN COUNTY OPEN DATA / SOCRATA / DATA.GOV ===")
data_urls = [
    "https://data.ca.gov/api/3/action/package_search?q=kern+assessor+parcel",
    "https://data.ca.gov/api/3/action/package_search?q=kern+property+tax",
    "https://catalog.data.gov/api/3/action/package_search?q=kern+county+assessor",
]
for url in data_urls:
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        d = r.json()
        results = d.get("result", {}).get("results", [])
        print(f"  {url} -> {r.status_code} | {len(results)} results")
        for item in results[:5]:
            print(f"    {item.get('title')} | {item.get('name')}")
    except Exception as e:
        print(f"  {url} -> {e}")
