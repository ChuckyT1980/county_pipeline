import requests, re, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'X-Requested-With': 'XMLHttpRequest',
})

# Try to get JSON response from search URL by adding ?f=JSON or similar
apn = '002271003000'
urls = [
    f'https://common2.mptsweb.com/MBC/butte/tax/search?f=Q&Asmt={apn}&TaxYear=2025&RollYear=',
    f'https://common2.mptsweb.com/MBC/butte/tax/search?Asmt={apn}&TaxYear=2025&RollYear=',
    f'https://common2.mptsweb.com/MBC/butte/tax/main/{apn}/2025/0000',
    f'https://common2.mptsweb.com/MBC/butte/tax/search?f=Q&Asmt={apn}&TaxYear=2025&RollYear=&format=json',
]

for url in urls:
    try:
        r = s.get(url, timeout=15)
        ct = r.headers.get('Content-Type', '')
        js = ''
        try:
            d = r.json()
            js = json.dumps(d)[:300]
        except:
            js = 'NOT JSON'
        print(f"URL: {url[:90]}")
        print(f"  Status: {r.status_code}, Content-Type: {ct}")
        print(f"  Body: {js}")
        print()
    except Exception as e:
        print(f"URL: {url[:90]}")
        print(f"  ERROR: {e}")
        print()
