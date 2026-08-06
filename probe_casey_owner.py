import requests, json
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
    'Accept': 'application/json, text/html, */*',
    'Referer': 'https://common1.mptsweb.com/mbc/tehama/tax/search',
})

# Test 1: MBC search landing page (to understand what form params exist)
print('=== TEST 1: MBC tax/search landing ===')
url1 = 'https://common1.mptsweb.com/mbc/tehama/tax/search'
r1 = s.get(url1, timeout=15)
print(f'Status: {r1.status_code}, len: {len(r1.text)}')
soup1 = BeautifulSoup(r1.text, 'html.parser')
for inp in soup1.find_all(['input', 'select', 'form']):
    print(' ', inp.name, inp.get('name'), inp.get('id'), inp.get('action'))
print()

# Test 2: Known MPTS API endpoints for name search
paths = [
    '/mbc/tehama/tax/search?name=casey',
    '/mbc/tehama/tax/search?ownername=casey',
    '/mbc/tehama/asr/search?name=casey',
    '/mbap/tehama/asr/search?name=casey',
    '/MBC/api/search/tehama?name=casey',
    '/mbc/tehama/tax/parcelSearch?searchType=name&searchValue=casey',
]

print('=== TEST 2: Name search path probes ===')
for path in paths:
    url = 'https://common1.mptsweb.com' + path
    try:
        r = s.get(url, timeout=10)
        ct = r.headers.get('content-type', '')
        print(f'{path} -> {r.status_code}, len={len(r.text)}, ct={ct}')
        if r.status_code == 200 and len(r.text) > 200:
            print('  SAMPLE:', r.text[:400])
    except Exception as e:
        print(f'{path} -> ERROR: {e}')

# Test 3: POST form submission for name search
print()
print('=== TEST 3: POST name search ===')
post_url = 'https://common1.mptsweb.com/mbc/tehama/tax/search'
for data in [
    {'searchType': 'name', 'searchValue': 'casey'},
    {'owner': 'casey', 'type': 'owner'},
    {'name': 'casey'},
]:
    try:
        r = s.post(post_url, data=data, timeout=10)
        ct = r.headers.get('content-type', '')
        print(f'POST {data} -> {r.status_code}, len={len(r.text)}, ct={ct}')
        if r.status_code == 200 and len(r.text) > 200:
            print('  SAMPLE:', r.text[:400])
    except Exception as e:
        print(f'POST {data} -> ERROR: {e}')

# Test 4: Try the TaxBillv2 with just the APN directly (no roll_cat needed)
print()
print('=== TEST 4: TaxBillv2 direct APN lookup ===')
apn = '305073053000'
for roll_cat in ['CS', 'RP', 'PP', 'US']:
    url = f'https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx?CN=tehama&Asmt={apn}&TaxYear=2025&RollCat={roll_cat}&RollType=S&RollYear='
    try:
        r = s.get(url, timeout=10)
        ct = r.headers.get('content-type', '')
        print(f'RollCat={roll_cat} -> {r.status_code}, len={len(r.text)}')
        if r.status_code == 200 and len(r.text) > 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            text = soup.get_text(separator=' | ')
            print('  TEXT:', text[:800])
            break
    except Exception as e:
        print(f'RollCat={roll_cat} -> ERROR: {e}')
