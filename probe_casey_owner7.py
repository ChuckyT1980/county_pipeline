"""
Probe 7:
1. Try tax.tehama.gov (the View/Pay Taxes portal - likely MPTS hosted)
2. Try the ArcGIS parcel viewer for Tehama County - search by APN
3. Try the MPTS common3 MegabyteCommonSite public inquiry with proper session
4. Look for the APN in any GIS REST service
"""
import requests, re
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
})

APN = '305-073-053-000'
APN_CLEAN = '305073053000'

# ── 1. tax.tehama.gov ─────────────────────────────────────────────────────────
print('=== TAX.TEHAMA.GOV ===')
try:
    rt = s.get('http://tax.tehama.gov', timeout=15, allow_redirects=True)
    print(f'Status: {rt.status_code}, final URL: {rt.url}, len={len(rt.text)}')
    soup_t = BeautifulSoup(rt.text, 'html.parser')
    title = soup_t.find('title')
    print(f'Title: {title.get_text() if title else "?"}')
    print()
    print('Form fields:')
    for inp in soup_t.find_all(['input', 'select', 'form']):
        print(f'  {inp.name}: id={inp.get("id")} name={inp.get("name")} type={inp.get("type","?")} value={str(inp.get("value",""))[:50]}')
    print()
    print('Links:')
    for link in soup_t.find_all('a', href=True)[:20]:
        txt = link.get_text(strip=True)
        href = link['href']
        if txt:
            print(f'  {txt[:50]} -> {href[:80]}')
except Exception as e:
    print(f'ERROR: {e}')

print()

# ── 2. MPTS common3 MegabyteCommonSite Public Inquiry ────────────────────────
print('=== MPTS COMMON3 PUBLIC INQUIRY ===')
# This is a different MPTS entry point - common3 vs common1
# The URL from assessor page was:
# https://common3.mptsweb.com/MegabyteCommonSite/(S(zm1fp4au5zfepbuitord4iop))/PublicInquiry/Inquiry.aspx?CN=tehama&SITE=Public&DEPT=Asr&PG=Search
# Try without the session token
mpts3_urls = [
    'https://common3.mptsweb.com/MegabyteCommonSite/PublicInquiry/Inquiry.aspx?CN=tehama&SITE=Public&DEPT=Asr&PG=Search',
    'https://common3.mptsweb.com/MegabyteCommonSite/PublicInquiry/Inquiry.aspx?CN=tehama&SITE=Public&DEPT=Asr&PG=Result&APN=' + APN_CLEAN,
]
for url in mpts3_urls:
    try:
        r = s.get(url, timeout=15, allow_redirects=True)
        print(f'{url[:80]} -> {r.status_code}, len={len(r.text)}, final={r.url[:80]}')
        if r.status_code == 200:
            soup3 = BeautifulSoup(r.text, 'html.parser')
            title = soup3.find('title')
            print(f'  Title: {title.get_text() if title else "?"}')
            for inp in soup3.find_all(['input','select'])[:10]:
                print(f'  Field: {inp.get("name")} id={inp.get("id")} value={str(inp.get("value",""))[:40]}')
            # Look for any output with our APN
            text = soup3.get_text(separator='|')
            if APN_CLEAN in text or APN in text:
                print(f'  *** APN FOUND IN RESPONSE ***')
                idx = text.find(APN_CLEAN if APN_CLEAN in text else APN)
                print(f'  Context: {text[max(0,idx-100):idx+200]}')
    except Exception as e:
        print(f'{url[:80]} -> ERROR: {e}')

print()

# ── 3. ArcGIS Tehama County Parcel data ──────────────────────────────────────
print('=== ARCGIS TEHAMA PARCEL VIEWER ===')
# The ArcGIS webmap from the assessor page - try to find the feature service behind it
arcgis_urls = [
    # Try to query the ArcGIS REST directly for this APN
    'https://services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services?f=json',
    # Try common Tehama County ArcGIS servers
    'https://services1.arcgis.com/abc123/arcgis/rest/services',
    # The webmap ID from assessor link: 341b39221caf4cfba2864425b93fdfaf
    'https://www.arcgis.com/sharing/rest/content/items/341b39221caf4cfba2864425b93fdfaf?f=json',
]
for url in arcgis_urls:
    try:
        r = s.get(url, timeout=10)
        ct = r.headers.get('content-type', '')
        print(f'{url[:80]} -> {r.status_code}, len={len(r.text)}, ct={ct}')
        if r.status_code == 200 and 'json' in ct:
            import json
            data = r.json()
            print(f'  Keys: {list(data.keys())[:10]}')
            if 'operationalLayers' in data:
                for layer in data.get('operationalLayers', [])[:5]:
                    print(f'  Layer: {layer.get("title")} url={layer.get("url","")}')
    except Exception as e:
        print(f'{url[:80]} -> ERROR: {e}')

print()

# ── 4. Try MPTS common1 with the APN in different format patterns ─────────────
print('=== MPTS: APN FORMAT VARIATIONS ===')
# Maybe the APN uses a different format in MPTS - try different zero-padding and separators
apn_variants = [
    '305073053000',  # 12-digit compact
    '305-073-053-000',  # standard Tehama format
    '305073053',  # 9-digit without trailing zeros
    '305-073-053',  # without last segment
    '030507305300',  # zero-padded differently
]

for apn_v in apn_variants:
    url = f'https://common1.mptsweb.com/mbap/tehama/asr/AsrPrint/{apn_v}'
    try:
        r = s.get(url, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        rows = soup.find_all('tr')
        has_data = False
        for tr in rows:
            cells = [c.get_text(strip=True) for c in tr.find_all(['td','th'])]
            if len(cells) >= 2 and cells[1].strip():
                has_data = True
                break
        print(f'APN {apn_v}: {r.status_code}, len={len(r.text)}, has_data={has_data}')
        if has_data:
            for tr in rows:
                cells = [c.get_text(strip=True) for c in tr.find_all(['td','th'])]
                if cells and any(c.strip() for c in cells):
                    print(f'  {cells}')
    except Exception as e:
        print(f'APN {apn_v}: ERROR {e}')

print()

# ── 5. Try the Tehama County parcel query via GIS link from assessor page ─────
print('=== TEHAMA GIS PARCEL LOOKUP ===')
gis_urls = [
    'https://www.tehamacountypublicworks.ca.gov/gis.html',
    'https://tehama.maps.arcgis.com/home/webmap/viewer.html?webmap=a9c3ebafce0b4a36ad6031964fb5251f',
]
for url in gis_urls:
    try:
        r = s.get(url, timeout=10)
        print(f'{url[:80]} -> {r.status_code}, len={len(r.text)}')
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            # Look for any REST service links
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'arcgis' in href.lower() or 'rest' in href.lower() or 'service' in href.lower():
                    print(f'  GIS link: {link.get_text(strip=True)[:40]} -> {href[:80]}')
    except Exception as e:
        print(f'{url[:80]} -> ERROR: {e}')
