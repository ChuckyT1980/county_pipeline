import requests, json

asmt = '002271003000'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0', 'X-Requested-With': 'XMLHttpRequest'})

r = s.get(f'https://common2.mptsweb.com/MBC/api/search/butte/0000-CURR/feeparcel/{asmt}', timeout=10)
print(f'Status: {r.status_code}')
ct = r.headers.get('content-type', '')
print(f'Content-Type: {ct}')
print(f'Length: {len(r.text)}')
print(f'First 500 chars: {r.text[:500]}')

if r.status_code == 200:
    data = r.json()
    if isinstance(data, str):
        data = json.loads(data)
    print(json.dumps(data, indent=2)[:2000])
