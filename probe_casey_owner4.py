"""
Probe 4: 
1. Find the actual Tehama County DocumentCenter URL structure - crawl their sitemap/navigation
2. Try archive.org for the auction list PDF  
3. Try the Tehama County tax collector page for auction docs
4. Check if APN 305-073-053-000 is a valid Tehama APN - the format may be different
   (Tehama goes up to ~103xxx in MPTS, but county APN map may use different numbering)
"""
import requests, re, json
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
})

# ── 1. Tehama County main site - find auction/tax sale pages ─────────────────
print('=== TEHAMA COUNTY WEBSITE: Find tax sale pages ===')
r = s.get('https://www.tehamacounty.ca.gov', timeout=15)
print(f'Main site: {r.status_code}, len={len(r.text)}')
soup = BeautifulSoup(r.text, 'html.parser')

# Find all links with tax/auction keywords
for link in soup.find_all('a', href=True):
    href = link['href']
    txt = link.get_text(strip=True)
    if any(kw in txt.lower() or kw in href.lower() for kw in ['tax', 'auction', 'sale', 'collector', 'assessor', 'treasurer']):
        full_href = href if href.startswith('http') else f'https://www.tehamacounty.ca.gov{href}'
        print(f'  {txt[:60]} -> {full_href}')

print()

# ── 2. Tax Collector page ─────────────────────────────────────────────────────
print('=== TAX COLLECTOR PAGE ===')
tc_urls = [
    'https://www.tehamacounty.ca.gov/government/departments/tax-collector',
    'https://www.tehamacounty.ca.gov/government/departments/treasurer-tax-collector',
    'https://www.tehamacounty.ca.gov/255/Tax-Collector',
    'https://www.tehamacounty.ca.gov/256/Treasurer-Tax-Collector',
]
for url in tc_urls:
    try:
        r = s.get(url, timeout=10)
        print(f'{url} -> {r.status_code}, len={len(r.text)}')
        if r.status_code == 200:
            soup_tc = BeautifulSoup(r.text, 'html.parser')
            for link in soup_tc.find_all('a', href=True):
                href = link['href']
                txt = link.get_text(strip=True)
                if any(kw in txt.lower() or kw in href.lower() for kw in ['auction', 'sale', 'delinquent', 'document', 'pdf', 'list']):
                    full_href = href if href.startswith('http') else f'https://www.tehamacounty.ca.gov{href}'
                    print(f'  LINK: {txt[:60]} -> {full_href}')
            break
    except Exception as e:
        print(f'{url} -> ERROR: {e}')

print()

# ── 3. Archive.org for auction list ──────────────────────────────────────────
print('=== ARCHIVE.ORG: Tehama auction list ===')
# Check archive.org CDX API for this URL pattern
cdx_url = 'http://web.archive.org/cdx/search/cdx?url=tehamacounty.ca.gov/DocumentCenter/View/138179*&output=json&limit=5&fl=timestamp,original,statuscode,mimetype'
try:
    ar = s.get(cdx_url, timeout=15)
    print(f'CDX status: {ar.status_code}')
    if ar.status_code == 200:
        data = ar.json()
        print(f'CDX results: {len(data)}')
        for row in data[:10]:
            print(f'  {row}')
except Exception as e:
    print(f'CDX ERROR: {e}')

# Also search for any Tehama auction PDFs in archive
cdx_url2 = 'http://web.archive.org/cdx/search/cdx?url=tehamacounty.ca.gov/*auction*&output=json&limit=10&fl=timestamp,original,statuscode,mimetype'
try:
    ar2 = s.get(cdx_url2, timeout=15)
    if ar2.status_code == 200:
        data2 = ar2.json()
        print(f'Archive auction CDX results: {len(data2)}')
        for row in data2[:10]:
            print(f'  {row}')
except Exception as e:
    print(f'Archive auction CDX ERROR: {e}')

print()

# ── 4. Check the Tehama County DocumentCenter for all documents in range ──────
print('=== DOCUMENTCENTER: Scan nearby IDs ===')
# The 404 pages were 103KB - meaning they hit the CivicPlus 404 template
# Let's try a range of doc IDs around 138179 to find valid ones
found_docs = []
for doc_id in range(138160, 138200):
    url = f'https://www.tehamacounty.ca.gov/DocumentCenter/View/{doc_id}'
    try:
        r = s.get(url, timeout=8, allow_redirects=True)
        ct = r.headers.get('content-type', '')
        size = len(r.content)
        # Valid docs usually redirect to a PDF or return a different page than the 404
        # The 404 page was 103617 bytes
        if r.status_code == 200 and size != 103602 and size != 103604 and size != 103617:
            print(f'  POSSIBLE DOC {doc_id}: status={r.status_code}, size={size}, ct={ct}, url={r.url}')
            found_docs.append(doc_id)
        elif r.status_code in [301, 302]:
            print(f'  REDIRECT {doc_id}: -> {r.headers.get("location")}')
    except Exception as e:
        pass

print(f'Found {len(found_docs)} possible valid docs near 138179')
