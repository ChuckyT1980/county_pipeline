"""
audit_fresno_raw_sources.py — Zero-Assumptions Fresno Raw Source Audit
====================================================================
Tests every raw endpoint for Fresno County (Assessor, Recorder, Tax Collector)
and prints un-merged raw response payloads, HTTP status codes, and security gate status.
"""

import requests, json, sqlite3, os
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}

print("==========================================================================")
print("FRESNO COUNTY RAW SOURCE & ENDPOINT AUDIT")
print("==========================================================================")

# ---------------------------------------------------------------------------
# 1. ASSESSOR ENDPOINT AUDIT
# ---------------------------------------------------------------------------
assessor_urls = [
    "https://services.arcgis.com/fresno/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=1&f=json",
    "https://gisportal.co.fresno.ca.us/arcgis/rest/services/Public/Parcels/MapServer/0/query?where=1%3D1&outFields=*&resultRecordCount=1&f=json"
]

print("\n--- [SOURCE 1: FRESNO ASSESSOR / GIS] ---")
for url in assessor_urls:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"URL: {url}")
        print(f"  -> HTTP Status: {r.status_code}")
        print(f"  -> Response Size: {len(r.text):,d} bytes")
        print(f"  -> Has CAPTCHA/Login Wall: {'captcha' in r.text.lower() or 'login' in r.text.lower() or 'access denied' in r.text.lower()}")
        print(f"  -> Raw Payload Snippet:\n{r.text[:350]}\n")
    except Exception as e:
        print(f"URL: {url} -> EXCEPTION: {e}\n")

# ---------------------------------------------------------------------------
# 2. RECORDER ENDPOINT AUDIT (Tyler EagleWeb Fresno)
# ---------------------------------------------------------------------------
recorder_url = "https://fresnocountyca-web.tylerhost.net/recorder/web/login.jsp"
print("\n--- [SOURCE 2: FRESNO RECORDER / TYLER EAGLEWEB] ---")
try:
    r = requests.get(recorder_url, headers=headers, timeout=10, allow_redirects=True)
    print(f"URL: {recorder_url}")
    print(f"  -> HTTP Status: {r.status_code}")
    print(f"  -> Response Size: {len(r.text):,d} bytes")
    has_gate = any(kw in r.text.lower() for kw in ["recaptcha", "g-recaptcha", "login", "session", "disclaimer", "accept"])
    print(f"  -> Has CAPTCHA/Disclaimer/Login Wall: {has_gate}")
    print(f"  -> Raw Payload Snippet:\n{r.text[:350]}\n")
except Exception as e:
    print(f"URL: {recorder_url} -> EXCEPTION: {e}\n")

# ---------------------------------------------------------------------------
# 3. TAX COLLECTOR / EXCESS PROCEEDS AUDIT
# ---------------------------------------------------------------------------
tax_file = "excess_proceeds/excess_proceeds_fresno_2025.csv"
print("\n--- [SOURCE 3: FRESNO TAX COLLECTOR / EXCESS PROCEEDS SOURCE FILE] ---")
if os.path.exists(tax_file):
    with open(tax_file, encoding="utf-8") as f:
        content = f.read()
        print(f"File Path: {tax_file}")
        print(f"  -> Size: {len(content):,d} bytes")
        print(f"  -> First 3 Raw Records:\n" + "\n".join(content.splitlines()[:4]))
else:
    print(f"File Path: {tax_file} -> NOT FOUND")

# ---------------------------------------------------------------------------
# 4. PARCEL STATE DATABASE SAMPLE RECORD
# ---------------------------------------------------------------------------
db_path = "data/counties/fresno/state.sqlite"
print("\n--- [SOURCE 4: FRESNO LOCAL STATE.SQLITE UN-MERGED RECORD] ---")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM parcels WHERE owner IS NOT NULL AND owner != '' LIMIT 1").fetchone()
    if row:
        print(dict(row))
    conn.close()
