"""Check if the MBC search API returns owner names"""
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

# Search by feeparcel prefix - this APN should return the lead we know
url = 'https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/070050072'
r = S.get(url, timeout=10)
raw = r.json()
if isinstance(raw, str):
    data = json.loads(raw)
else:
    data = raw

row = data.get('Table', {}).get('Row', [])
if isinstance(row, dict):
    row = [row]  # Single result case

print('Number of rows:', len(row))
if row:
    print('All keys in first row:')
    for k in sorted(row[0].keys()):
        print('  %s: %s' % (k, row[0].get(k, '')))

# Check for Owner in ALL rows
print()
print('Checking all rows for Owner field:')
for i, r2 in enumerate(row):
    owner = r2.get('Owner') or r2.get('owner') or r2.get('OWNER')
    print('  Row %d: Owner=%s' % (i, owner))

# Also check for the sample URL we know works
url2 = 'https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/018600041'
r2 = S.get(url2, timeout=10)
raw2 = r2.json()
if isinstance(raw2, str):
    data2 = json.loads(raw2)
else:
    data2 = raw2
row2 = data2.get('Table', {}).get('Row', [])
if isinstance(row2, dict):
    row2 = [row2]
print()
print('APN 018-600-041-000 (Dee Knoch Rd, $16K balance):')
for r3 in row2:
    owner = r3.get('Owner') or r3.get('owner') or r3.get('OWNER')
    print('  Keys:', sorted(r3.keys()))
    print('  Owner:', owner)
    for k, v in r3.items():
        print('  %s: %s' % (k, v))
