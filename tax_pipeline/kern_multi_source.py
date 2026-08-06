"""
Kern County Multi-Source Live Scraper
Tries every available real data source in priority order:
1. Kern County tax sale brochure PDF (already downloaded)
2. Kern County Open Data Portal (ArcGIS Hub) parcel search
3. KCTTC property search via direct URL patterns (no CAPTCHA)
4. County assessor APN roll via alternative GIS endpoints
5. PublicRecord.com / Kern FOIA published parcel data
"""
import os, sys, re, json, time, requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
BASE = r"C:\Users\chuck\Downloads\county_pipeline\kern"

# ──────────────────────────────────────────────
# 1. EXTRACT TEXT FROM THE KCTTC TAX SALE BROCHURE PDF
# ──────────────────────────────────────────────
def try_pdf_extract():
    print("\n=== [1] PARSING KCTTC TAX SALE BROCHURE PDF ===")
    pdf_path = os.path.join(BASE, "taxsalebrochure.pdf")
    if not os.path.exists(pdf_path):
        print("  PDF not found.")
        return

    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            print(f"  PDF pages: {len(pdf.pages)}")
            for i, page in enumerate(pdf.pages[:5]):
                text = page.extract_text() or ""
                if text.strip():
                    print(f"\n  --- PAGE {i+1} ---")
                    print(text[:1000])
            # Look for APN patterns in all pages
            all_text = ""
            for page in pdf.pages:
                all_text += (page.extract_text() or "") + "\n"
            apn_pattern = re.compile(r'\b\d{3}-\d{3}-\d{2,3}\b')
            apns_found = list(set(apn_pattern.findall(all_text)))
            print(f"\n  APNs found in PDF: {len(apns_found)}")
            for a in apns_found[:20]:
                print(f"    {a}")
    except ImportError:
        print("  pdfplumber not installed. Trying pypdf2...")
        try:
            import PyPDF2
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                print(f"  PDF pages: {len(reader.pages)}")
                for i in range(min(5, len(reader.pages))):
                    text = reader.pages[i].extract_text() or ""
                    print(f"\n  --- PAGE {i+1} ---")
                    print(text[:1000])
        except ImportError:
            print("  Neither pdfplumber nor PyPDF2 available.")

# ──────────────────────────────────────────────
# 2. KERN COUNTY OPEN DATA PORTAL (ArcGIS Hub)
# ──────────────────────────────────────────────
def try_opendata_hub():
    print("\n=== [2] KERN COUNTY OPEN DATA PORTAL / ARCGIS HUB ===")
    urls = [
        "https://hub.arcgis.com/api/v3/datasets?q=kern+parcel&filter%5Btype%5D=Feature+Layer&page%5Bsize%5D=10",
        "https://opendata.kerncounty.com/api/v1/meta",
        "https://data.kerncounty.com/resource/",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8)
            print(f"  {url} -> {r.status_code} ({len(r.text)} bytes)")
            if r.status_code == 200:
                try:
                    d = r.json()
                    if isinstance(d, dict):
                        print(f"  Keys: {list(d.keys())[:8]}")
                    elif isinstance(d, list):
                        print(f"  Items: {len(d)}")
                        if d:
                            print(f"  First item keys: {list(d[0].keys())[:8]}")
                except:
                    print(f"  Raw (first 300): {r.text[:300]}")
        except Exception as e:
            print(f"  {url} -> ERROR: {e}")

# ──────────────────────────────────────────────
# 3. KERN ARCGIS HUB PARCEL SEARCH
# ──────────────────────────────────────────────
def try_arcgis_hub_search():
    print("\n=== [3] ARCGIS HUB KERN PARCEL FEATURE SERVICE SEARCH ===")
    search_url = "https://www.arcgis.com/sharing/rest/search"
    params = {
        "q": "kern county parcels tax delinquent owner",
        "f": "json",
        "num": 10,
        "sortField": "numviews",
        "sortOrder": "desc"
    }
    try:
        r = requests.get(search_url, params=params, headers=HEADERS, timeout=10)
        print(f"  ArcGIS search status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            print(f"  Results: {len(results)}")
            for item in results:
                print(f"\n  Title: {item.get('title')}")
                print(f"  Type: {item.get('type')}")
                print(f"  URL: {item.get('url')}")
                print(f"  Owner: {item.get('owner')}")
    except Exception as e:
        print(f"  ERROR: {e}")

# ──────────────────────────────────────────────
# 4. KCTTC DIRECT PROPERTY LOOKUP PATTERNS (NO CAPTCHA ROUTES)
# ──────────────────────────────────────────────
def try_direct_kcttc_patterns():
    print("\n=== [4] KCTTC DIRECT URL PATTERN PROBES (NON-CAPTCHA ROUTES) ===")
    patterns = [
        "https://www.kcttc.co.kern.ca.us/Payment/PaymentDetail.aspx?APN=00110001",
        "https://www.kcttc.co.kern.ca.us/Payment/PaymentDetail.aspx?APN=001-100-01",
        "https://www.kcttc.co.kern.ca.us/taxbillview.cfm?apn=001-100-01",
        "https://www.kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showDefaultedProperty",
        "https://www.kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showTaxDefaultedProperties",
        "https://www.kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showTaxSaleList",
        "https://www.kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showTaxSaleProperties",
    ]
    for url in patterns:
        try:
            r = requests.get(url, headers=HEADERS, timeout=6)
            soup = BeautifulSoup(r.text, "html.parser")
            title = soup.title.text.strip() if soup.title else "no title"
            print(f"  {url}")
            print(f"    -> {r.status_code} ({len(r.text)} bytes) | Title: {title}")
        except Exception as e:
            print(f"  {url} -> ERROR: {e}")

# ──────────────────────────────────────────────
# 5. KERN COUNTY ASSESSOR DIRECT PORTAL
# ──────────────────────────────────────────────
def try_assessor_portal():
    print("\n=== [5] KERN COUNTY ASSESSOR / RECORDER PORTAL PROBES ===")
    urls = [
        "https://www.assessor.co.kern.ca.us/",
        "https://kcttc.co.kern.ca.us/propertytax/",
        "https://assessor.kerncounty.com/",
        "https://kernassessor.com/",
        "https://www.kernassessor.com/",
        "https://kernco.gov/assessor",
        "https://www.kerncounty.com/government/departments/assessor",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=6)
            soup = BeautifulSoup(r.text, "html.parser")
            title = soup.title.text.strip() if soup.title else "no title"
            print(f"  {url} -> {r.status_code} | {title[:80]}")
        except Exception as e:
            print(f"  {url} -> ERROR: {e}")

if __name__ == "__main__":
    try_pdf_extract()
    try_opendata_hub()
    try_arcgis_hub_search()
    try_direct_kcttc_patterns()
    try_assessor_portal()
    print("\n=== ALL PROBES COMPLETE ===")
