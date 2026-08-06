"""
Probe 5: 
1. Hit the real tehama.gov tax sale auctions page - find auction list PDF
2. Try the Tehama Assessor page on tehama.gov
3. Use the Tyler EagleWeb properly - the NAMESEARCH page is actually accessible
"""
import requests, re
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
})

# ── 1. Tax Sale Auctions page ─────────────────────────────────────────────────
print('=== TAX SALE AUCTIONS PAGE ===')
url = 'https://www.tehama.gov/government/departments/treasurer-tax-collector/tax-sale-auctions/'
r = s.get(url, timeout=15)
print(f'Status: {r.status_code}, len={len(r.text)}')
soup = BeautifulSoup(r.text, 'html.parser')

# Find all PDF links
print('PDF links:')
for link in soup.find_all('a', href=True):
    href = link['href']
    txt = link.get_text(strip=True)
    if '.pdf' in href.lower() or 'auction' in href.lower() or 'auction' in txt.lower() or 'list' in txt.lower() or 'sale' in txt.lower():
        full_href = href if href.startswith('http') else f'https://www.tehama.gov{href}'
        print(f'  {txt[:70]} -> {full_href}')

print()
print('ALL links on the page:')
for link in soup.find_all('a', href=True):
    href = link['href']
    txt = link.get_text(strip=True)
    if txt and href and not href.startswith('#'):
        full_href = href if href.startswith('http') else f'https://www.tehama.gov{href}'
        print(f'  {txt[:60]} -> {full_href}')

print()

# ── 2. Tehama Assessor page ───────────────────────────────────────────────────
print('=== TEHAMA ASSESSOR PAGE ===')
asr_url = 'https://www.tehama.gov/government/departments/assessor/'
ra = s.get(asr_url, timeout=15)
print(f'Status: {ra.status_code}, len={len(ra.text)}')
soup_a = BeautifulSoup(ra.text, 'html.parser')
for link in soup_a.find_all('a', href=True):
    href = link['href']
    txt = link.get_text(strip=True)
    if txt and href and not href.startswith('#'):
        full_href = href if href.startswith('http') else f'https://www.tehama.gov{href}'
        if any(kw in txt.lower() or kw in href.lower() for kw in ['parcel', 'search', 'gis', 'map', 'property', 'lookup']):
            print(f'  {txt[:60]} -> {full_href}')

print()

# ── 3. Try Tyler EagleWeb NAMESEARCH - POST properly with disclaimer ──────────
print('=== TYLER EAGLEWEB: NAMESEARCH with proper disclaimer flow ===')
TYLER = 'https://recordsearch.tehama.gov'

# Get the NAMESEARCH page directly
rn = s.get(f'{TYLER}/web/search/NAMESEARCH4S1', timeout=15)
print(f'NAMESEARCH landing: {rn.status_code}, len={len(rn.text)}')
soup_n = BeautifulSoup(rn.text, 'html.parser')

# Print all inputs
print('NAMESEARCH form fields:')
for inp in soup_n.find_all(['input', 'select', 'textarea', 'button']):
    print(f'  {inp.name}: id={inp.get("id")} name={inp.get("name")} type={inp.get("type")} value={str(inp.get("value",""))[:60]}')

# Look at all scripts for JS clues  
print()
print('Scripts with relevant content:')
for sc in soup_n.find_all('script'):
    text = sc.get_text()
    if len(text) > 50 and ('search' in text.lower() or 'disclaimer' in text.lower() or 'casey' in text.lower()):
        print(f'  Script: {text[:400]}')

# Try posting to NAMESEARCH  
print()
print('Posting name CASEY to NAMESEARCH:')
post_data = {
    'field_BothNamesID': 'CASEY',
    'field_LastNameID': 'CASEY',
    'searchButton': 'Search',
    'submitSearch': 'Search',
}
for key_subset in [
    {'field_BothNamesID': 'CASEY'},
    {'field_LastNameID': 'CASEY', 'field_FirstNameID': ''},
    {'LastName': 'CASEY'},
    {'grantorGrantee': 'CASEY'},
]:
    rp = s.post(f'{TYLER}/web/search/NAMESEARCH4S1', data=key_subset, timeout=15)
    soup_p = BeautifulSoup(rp.text, 'html.parser')
    rows = soup_p.find_all('li', class_='ss-search-row')
    rows2 = soup_p.find_all('tr')
    td_rows = [tr for tr in rows2 if tr.find('td')]
    print(f'  POST {list(key_subset.keys())} -> {rp.status_code}, li.rows={len(rows)}, tr.rows={len(td_rows)}')
    if rows:
        for row in rows[:3]:
            print(f'    ROW: {row.get_text(separator="|", strip=True)[:200]}')
    if td_rows:
        for tr in td_rows[:3]:
            cells = [c.get_text(strip=True) for c in tr.find_all(['td','th'])]
            print(f'    TR: {cells}')

print()

# ── 4. Try direct REST API on Tyler recorder ─────────────────────────────────
print('=== TYLER API ENDPOINTS ===')
api_paths = [
    '/api/search?name=CASEY',
    '/api/v1/search?grantorGrantee=CASEY',
    '/web/api/search?name=CASEY',
    '/api/search/grantor?name=CASEY',
]
for path in api_paths:
    try:
        rapi = s.get(f'{TYLER}{path}', timeout=10)
        ct = rapi.headers.get('content-type', '')
        print(f'{path} -> {rapi.status_code}, len={len(rapi.text)}, ct={ct}')
        if rapi.status_code == 200 and 'json' in ct:
            print(f'  JSON: {rapi.text[:300]}')
    except Exception as e:
        print(f'{path} -> ERROR: {e}')
