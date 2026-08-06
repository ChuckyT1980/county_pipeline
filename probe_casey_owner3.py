"""
Probe 3: 
1. Tyler EagleWeb recorder - accept disclaimer, then search by doc/APN
2. Tehama County public assessor website direct
3. Check if APN 305-073-053-000 is in a different APN scheme (section/township/range vs book/page/parcel)
4. Try the Tehama County GIS / parcel viewer
"""
import requests, re
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
})

APN = '305073053000'
APN_DASH = '305-073-053-000'

# ── 1. Tyler EagleWeb recorder - disclaimer + doc search by APN ──────────────
print('=== TYLER EAGLEWEB: Accept disclaimer + APN search ===')
TYLER = 'https://recordsearch.tehama.gov'

# Step 1: Get disclaimer page
r1 = s.get(f'{TYLER}/web/search/DOCSEARCH4S1', timeout=15)
soup1 = BeautifulSoup(r1.text, 'html.parser')

# Accept disclaimer  
disc_form = soup1.find('form')
disc_action = disc_form['action'] if disc_form and disc_form.get('action') else '/web/search/DOCSEARCH4S1'
disc_data = {}
for inp in soup1.find_all('input'):
    nm = inp.get('name')
    vl = inp.get('value', '')
    if nm:
        disc_data[nm] = vl

print(f'Disclaimer form action: {disc_action}')
print(f'Disclaimer form data keys: {list(disc_data.keys())}')
disc_data['submitDisclaimerAccept'] = 'Accept'

r2 = s.post(f'{TYLER}{disc_action}' if disc_action.startswith('/') else disc_action, 
            data=disc_data, timeout=15)
print(f'After disclaimer: {r2.status_code}, len={len(r2.text)}, url={r2.url}')
soup2 = BeautifulSoup(r2.text, 'html.parser')
title2 = soup2.find('title')
print(f'Title: {title2.get_text() if title2 else "?"}')

# Now look for the name search field
name_field = soup2.find(id='field_BothNamesID') or soup2.find(attrs={'name': 'field_BothNamesID'})
print(f'Name search field found: {name_field is not None}')

# Try to find search form
forms = soup2.find_all('form')
for f in forms[:3]:
    print(f'  Form action={f.get("action")} method={f.get("method")}')
    for inp in f.find_all(['input','select'])[:10]:
        print(f'    {inp.name} id={inp.get("id")} name={inp.get("name")} value={str(inp.get("value",""))[:40]}')

print()

# ── 2. Try name search directly on Tyler EagleWeb ────────────────────────────
print('=== TYLER: Name search for CASEY ===')
# Tyler uses specific URL pattern for name searches
name_search_urls = [
    f'{TYLER}/web/search/DOCSEARCH4S1',
    f'{TYLER}/web/search/NAMESEARCH4S1',
]
for nurl in name_search_urls:
    nr = s.get(nurl, timeout=10)
    print(f'{nurl} -> {nr.status_code}, len={len(nr.text)}')

# Try POST with name
post_data = {
    'field_BothNamesID': 'CASEY',
    'searchButton': 'Search',
}
nr2 = s.post(f'{TYLER}/web/search/DOCSEARCH4S1', data=post_data, timeout=15)
print(f'Name POST -> {nr2.status_code}, len={len(nr2.text)}')
soup_nr2 = BeautifulSoup(nr2.text, 'html.parser')
results = soup_nr2.find_all('li', class_='ss-search-row')
print(f'Search result rows: {len(results)}')
for row in results[:5]:
    print(f'  ROW: {row.get_text(separator="|", strip=True)[:200]}')

print()

# ── 3. Check Tehama County public assessor website ───────────────────────────
print('=== TEHAMA COUNTY ASSESSOR WEBSITE ===')
assessor_urls = [
    'https://www.tehamacounty.ca.gov/Departments/Assessor',
    'https://tehama.ca.gov/assessor',
    'https://assessor.tehamacounty.ca.gov',
    'https://www.tehamacounty.ca.gov/government/departments/assessor-recorder',
]
for aurl in assessor_urls:
    try:
        ar = s.get(aurl, timeout=10)
        print(f'{aurl} -> {ar.status_code}, len={len(ar.text)}')
        if ar.status_code == 200:
            # Look for parcel search links
            soup_a = BeautifulSoup(ar.text, 'html.parser')
            for link in soup_a.find_all('a', href=True):
                href = link['href']
                txt = link.get_text(strip=True)
                if any(kw in txt.lower() or kw in href.lower() for kw in ['parcel', 'search', 'assessor', 'property', 'apn']):
                    print(f'  LINK: {txt} -> {href}')
    except Exception as e:
        print(f'{aurl} -> ERROR: {e}')

print()

# ── 4. Try Tehama County GIS / parcel viewer ─────────────────────────────────
print('=== TEHAMA GIS / PARCEL VIEWER ===')
gis_urls = [
    f'https://gis.tehamacounty.ca.gov/arcgis/rest/services',
    f'https://www.tehamacounty.ca.gov/DocumentCenter/View/138179/Auction-List-',
    # Try different document IDs near 138179
    'https://www.tehamacounty.ca.gov/DocumentCenter/View/138178/',
    'https://www.tehamacounty.ca.gov/DocumentCenter/View/138180/',
    'https://www.tehamacounty.ca.gov/DocumentCenter/View/138179',
]
for gurl in gis_urls:
    try:
        gr = s.get(gurl, timeout=10, allow_redirects=True)
        ct = gr.headers.get('content-type', '')
        print(f'{gurl} -> {gr.status_code}, len={len(gr.content)}, ct={ct}')
        if gr.status_code == 200 and 'application/pdf' in ct:
            print('  *** PDF FOUND! ***')
        elif gr.status_code == 200:
            # Peek at content
            print(f'  SAMPLE: {gr.text[:200]}')
    except Exception as e:
        print(f'{gurl} -> ERROR: {e}')
