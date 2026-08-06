import requests, json, time

S = requests.Session()
S.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
})

S.get('https://common2.mptsweb.com/MBC/shasta/tax/search', timeout=15)
S.headers['Referer'] = 'https://common2.mptsweb.com/MBC/shasta/tax/search'
time.sleep(1)

url = 'https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/070050072'
r = S.get(url, timeout=10)
raw = r.json()
if isinstance(raw, str):
    data = json.loads(raw)
else:
    data = raw
print('Top-level keys:', list(data.keys()))
row = data.get('Table', {}).get('Row', [])
if isinstance(row, list) and len(row) > 0:
    print('Row keys:', list(row[0].keys()))
    print('First row values:')
    for k, v in row[0].items():
        print('  %s: %s' % (k, v))
    # Check for owner fields
    for r2 in row:
        for k in r2.keys():
            kl = k.lower()
            if any(x in kl for x in ['owner', 'name', 'assess', 'party', 'person', 'taxpayer']):
                print('FOUND: %s = %s' % (k, r2[k]))
else:
    print('No rows found or unexpected format:', type(row))
    print('Raw:', json.dumps(data, indent=2)[:1000])
