"""Check Tehama MBC tax API for owner names"""
import requests, json

url_fees = [
    '103040024000', '073260053000', '013220002000', '011390013000',
    '078400037000', '075250043000', '021230006000', '079330003000', '078270009000'
]

headers = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Referer': 'https://common2.mptsweb.com/'
}

for fee in url_fees:
    url = f'https://common2.mptsweb.com/MBC/api/search/tehama/0000-CURR/feeparcel/{fee}'
    try:
        r = requests.get(url, timeout=30, headers=headers)
        if r.status_code == 200:
            raw = r.text.strip()
            inner = json.loads(raw)
            data = json.loads(inner)
            row = data.get('Table', {}).get('Row', {})
            situs = row.get('Situs1', 'N/A')
            owner = row.get('Owner', 'N/A')
            print(f"{fee}: situs={situs} owner={owner}")
        else:
            print(f"{fee}: HTTP {r.status_code}")
    except Exception as e:
        print(f"{fee}: Error {e}")
