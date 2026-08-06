"""
Probe 2: 
1. Parse the actual MPTS MBC search form and submit properly with CSRF token
2. Try Tyler EagleWeb recorder name search for CASEY
3. Try MPTS MBC API JSON endpoints discovered from JS
"""
import requests, json, re
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
})

BASE = 'https://common1.mptsweb.com'
COUNTY = 'tehama'
APN = '305073053000'

# ── Step 1: Get the search page and extract form + CSRF token ─────────────────
print('=== STEP 1: Parse MBC search form ===')
search_url = f'{BASE}/mbc/{COUNTY}/tax/search'
r = s.get(search_url, timeout=15)
soup = BeautifulSoup(r.text, 'html.parser')

# Find CSRF token
csrf = soup.find('input', {'name': '__RequestVerificationToken'})
csrf_val = csrf['value'] if csrf else ''
print(f'CSRF token: {csrf_val[:30]}...' if csrf_val else 'No CSRF token found')

# Find the SearchVal select options
sel = soup.find('select', {'id': 'SearchVal'}) or soup.find('select', {'name': 'SearchVal'})
if sel:
    options = [(o.get('value'), o.get_text(strip=True)) for o in sel.find_all('option')]
    print(f'SearchVal options: {options}')

print()

# ── Step 2: Submit form with owner name search ────────────────────────────────
print('=== STEP 2: POST form - owner name search for CASEY ===')
# Try each possible owner-related SearchVal option
for search_val_opt in ['4', '3', '2', 'Owner', 'Name', 'OwnerName']:
    post_data = {
        '__RequestVerificationToken': csrf_val,
        'SearchVal': search_val_opt,
        'SearchValue': 'CASEY',
    }
    s.headers.update({'Referer': search_url, 'Content-Type': 'application/x-www-form-urlencoded'})
    rp = s.post(search_url, data=post_data, timeout=15)
    soup_r = BeautifulSoup(rp.text, 'html.parser')
    title = soup_r.find('title')
    results = soup_r.find_all('tr')
    non_header_rows = [tr for tr in results if tr.find('td')]
    print(f'SearchVal={search_val_opt} -> {rp.status_code}, rows={len(non_header_rows)}, title={title.get_text() if title else "?"}')
    if len(non_header_rows) > 0:
        for tr in non_header_rows[:5]:
            cells = [c.get_text(strip=True) for c in tr.find_all(['td','th'])]
            print(f'  ROW: {cells}')
        break

print()

# ── Step 3: Try the quick-search by fee parcel (APN direct) ──────────────────
print('=== STEP 3: Quick search by APN ===')
qs_data = {
    '__RequestVerificationToken': csrf_val,
    'quickSearchFeeParcel': APN,
}
s.headers.update({'Referer': search_url})
rq = s.post(search_url, data=qs_data, timeout=15)
soup_q = BeautifulSoup(rq.text, 'html.parser')
print(f'Quick APN search -> {rq.status_code}, len={len(rq.text)}')
for tr in soup_q.find_all('tr'):
    cells = [c.get_text(strip=True) for c in tr.find_all(['td','th'])]
    if cells and any(c.strip() for c in cells):
        print(f'  ROW: {cells}')

print()

# ── Step 4: Look for JSON/AJAX endpoints in the page JS ──────────────────────
print('=== STEP 4: Scan page JS for AJAX endpoint patterns ===')
r2 = s.get(search_url, timeout=15)
# Find all script tags
scripts = BeautifulSoup(r2.text, 'html.parser').find_all('script')
for sc in scripts:
    src = sc.get('src', '')
    text = sc.get_text()
    if 'api' in text.lower() or 'ajax' in text.lower() or 'json' in text.lower() or '/search' in text.lower():
        # Find URL-like patterns
        urls = re.findall(r'["\']([/][^\s"\'<>]+json[^\s"\'<>]*)["\']', text, re.I)
        urls += re.findall(r'["\']([/][^\s"\'<>]+/api/[^\s"\'<>]*)["\']', text, re.I)
        urls += re.findall(r'url\s*[:=]\s*["\']([^"\']+)["\']', text)
        if urls:
            print(f'Script URLs found: {urls[:10]}')
        # Print relevant snippet
        if 'SearchVal' in text or 'owner' in text.lower():
            print(f'SCRIPT with SearchVal/owner: {text[:500]}')

print()

# ── Step 5: Try Tyler EagleWeb recorder for name search (Tehama) ──────────────
print('=== STEP 5: Tyler EagleWeb recorder name search ===')
TYLER_BASE = 'https://recordsearch.tehama.gov'
# Get landing page to establish session/cookies
tr_r = s.get(f'{TYLER_BASE}/web/search/DOCSEARCH4S1', timeout=15)
print(f'Tyler landing: {tr_r.status_code}, len={len(tr_r.text)}')
tyler_soup = BeautifulSoup(tr_r.text, 'html.parser')

# Find disclaimer button
disclaimer = tyler_soup.find(id='submitDisclaimerAccept')
print(f'Disclaimer found: {disclaimer is not None}')

# Try to find the doc-type list or name-search endpoint
# Tyler EagleWeb uses a specific search form
for inp in tyler_soup.find_all(['input','select','form'])[:20]:
    n = inp.get('name') or inp.get('id') or ''
    v = inp.get('value') or ''
    if n:
        print(f'  Tyler form field: {inp.name} name={n} value={v[:50]}')
