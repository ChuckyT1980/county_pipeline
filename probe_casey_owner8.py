"""
Probe 8:
1. Parse ArcGIS org VYsrLd1WbPJ93eyz services list - find any Tehama parcel layer
2. Check if APN 305-073-053-000 appears in any ArcGIS feature service there
3. Also check: is this APN from a neighboring county that uses 3xx numbering?
   - Shasta County APN format check  
   - Trinity County
   - Glenn County
4. Try querying GovEase captured JSON files for this APN
"""
import requests, json, os, glob
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/html, */*',
})

APN = '305-073-053-000'
APN_CLEAN = '305073053000'

# ── 1. ArcGIS org services list ───────────────────────────────────────────────
print('=== ARCGIS ORG VYsrLd1WbPJ93eyz SERVICES ===')
r = s.get('https://services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services?f=json', timeout=20)
data = r.json()
services = data.get('services', [])
print(f'Total services: {len(services)}')
for svc in services:
    name = svc.get('name', '')
    svc_type = svc.get('type', '')
    url = svc.get('url', '')
    print(f'  {name} [{svc_type}]')
    if 'tehama' in name.lower() or 'parcel' in name.lower() or 'auction' in name.lower():
        print(f'    *** RELEVANT: {url}')

print()

# ── 2. Try querying Tehama-related ArcGIS layers ──────────────────────────────
print('=== QUERYING TEHAMA ARCGIS LAYERS ===')
# Filter to likely Tehama services
tehama_svcs = [s for s in services if 'tehama' in s.get('name','').lower()]
print(f'Tehama services: {len(tehama_svcs)}')
for svc in tehama_svcs:
    svc_url = f"https://services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services/{svc['name']}/{svc['type']}"
    try:
        ri = s.get(f'{svc_url}?f=json', timeout=10)
        svc_data = ri.json()
        layers = svc_data.get('layers', [])
        print(f'\n{svc["name"]}:')
        for layer in layers:
            print(f'  Layer {layer.get("id")}: {layer.get("name")}')
            # Try to query this layer for our APN
            query_url = f'{svc_url}/{layer["id"]}/query'
            params = {
                'where': f"APN='{APN}' OR APN='{APN_CLEAN}' OR PARCEL_NO='{APN}' OR ASSESSOR_NO='{APN}'",
                'outFields': '*',
                'f': 'json',
                'returnGeometry': False,
            }
            qr = s.get(query_url, params=params, timeout=10)
            if qr.status_code == 200:
                qdata = qr.json()
                features = qdata.get('features', [])
                print(f'    Query result: {len(features)} features')
                if features:
                    print(f'    MATCH: {json.dumps(features[0]["attributes"], indent=2)[:400]}')
    except Exception as e:
        print(f'  ERROR: {e}')

print()

# ── 3. Check GovEase captured JSON files for this APN ────────────────────────
print('=== GOVEASE CAPTURES: Search for APN 305-073-053 ===')
govease_files = glob.glob('kern/govease_captured_*.json')
print(f'Found {len(govease_files)} GovEase files')
found_count = 0
for gf in govease_files:
    try:
        with open(gf, 'r', encoding='utf-8') as f:
            content = f.read()
        if APN_CLEAN in content or APN in content or '305073053' in content:
            print(f'  MATCH in {gf}')
            data = json.loads(content)
            # Find the matching entry
            if isinstance(data, list):
                for item in data:
                    item_str = json.dumps(item)
                    if APN_CLEAN in item_str or APN in item_str:
                        print(f'    ITEM: {json.dumps(item, indent=2)[:500]}')
            found_count += 1
    except Exception as e:
        pass
print(f'Total files with match: {found_count}')

print()

# ── 4. Check if 305-xxx is a valid Shasta County APN format ───────────────────
print('=== SHASTA COUNTY: APN 305-073-053-000 probe ===')
# Shasta uses common2.mptsweb.com
shasta_url = f'https://common2.mptsweb.com/mbap/shasta/asr/AsrPrint/{APN_CLEAN}'
try:
    rs = s.get(shasta_url, timeout=10)
    soup = BeautifulSoup(rs.text, 'html.parser')
    has_data = False
    for tr in soup.find_all('tr'):
        cells = [c.get_text(strip=True) for c in tr.find_all(['td','th'])]
        if len(cells) >= 2 and cells[1].strip() and cells[0].strip():
            print(f'  SHASTA ROW: {cells}')
            has_data = True
    print(f'Shasta AsrPrint: {rs.status_code}, has_data={has_data}')
except Exception as e:
    print(f'Shasta ERROR: {e}')

print()

# ── 5. Check Butte MPTS for this APN ─────────────────────────────────────────
print('=== BUTTE COUNTY: APN 305-073-053-000 probe ===')
butte_url = f'https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/{APN_CLEAN}'
try:
    rb = s.get(butte_url, timeout=10)
    soup = BeautifulSoup(rb.text, 'html.parser')
    has_data = False
    for tr in soup.find_all('tr'):
        cells = [c.get_text(strip=True) for c in tr.find_all(['td','th'])]
        if len(cells) >= 2 and cells[1].strip() and cells[0].strip():
            print(f'  BUTTE ROW: {cells}')
            has_data = True
    print(f'Butte AsrPrint: {rb.status_code}, has_data={has_data}')
except Exception as e:
    print(f'Butte ERROR: {e}')

print()

# ── 6. Check the Tehama County Clerk/Recorder website for recorded docs ──────
print('=== TEHAMA CLERK/RECORDER ===')
cr_urls = [
    'https://www.tehama.gov/government/departments/clerk-and-recorder/',
]
for url in cr_urls:
    try:
        r = s.get(url, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        print(f'{url} -> {r.status_code}')
        for link in soup.find_all('a', href=True):
            href = link['href']
            txt = link.get_text(strip=True)
            if any(kw in txt.lower() or kw in href.lower() for kw in ['record', 'deed', 'document', 'search', 'index', 'grantor']):
                print(f'  LINK: {txt[:60]} -> {href[:80]}')
    except Exception as e:
        print(f'{url} -> ERROR: {e}')

print()

# ── 7. Try the Tehama Tax Sale 2025/2026 data from GovEase ───────────────────
print('=== GOVEASE LIVE: Tehama auction parcels ===')
govease_urls = [
    'https://liveauctions.govease.com/api/auctions?state=CA&county=Tehama',
    'https://liveauctions.govease.com/tehama',
    'https://liveauctions.govease.com/api/counties',
]
for url in govease_urls:
    try:
        r = s.get(url, timeout=10)
        ct = r.headers.get('content-type', '')
        print(f'{url} -> {r.status_code}, len={len(r.text)}, ct={ct}')
        if r.status_code == 200:
            print(f'  SAMPLE: {r.text[:300]}')
    except Exception as e:
        print(f'{url} -> ERROR: {e}')
