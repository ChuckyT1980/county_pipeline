import requests, json

s = requests.Session()
s.headers.update({'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json, text/javascript, */*'})

# Test Shasta book 064 for actual data
for prefix in ['064010', '064020', '064050', '064100']:
    r = s.get('https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/%s' % prefix, timeout=10)
    try:
        text = r.text
        data = json.loads(json.loads(text)) if text.startswith('"') else r.json()
        rows = data.get('Table', {}).get('Row', [])
        if isinstance(rows, dict):
            rows = [rows]
        real = [rw for rw in rows if rw.get('Asmt') and rw.get('Asmt') != 'null']
        print('prefix %s: %d rows, %d real' % (prefix, len(rows), len(real)))
        if real:
            print('  sample:', real[0])
    except Exception as e:
        print('prefix %s ERROR: %s' % (prefix, str(e)[:80]))

print()
print('Shasta stage2 verify URL test:')
# check if Shasta tax verify portal is up
try:
    r2 = s.get('https://common2.mptsweb.com/MBC/shasta/tax/main/064010001000/2025/0000', timeout=10)
    print('Shasta tax verify:', r2.status_code, r2.text[:150])
except Exception as e:
    print('Shasta tax verify ERROR:', e)

print()
print('Lassen portal test:')
for host in ['common1', 'common2', 'common3', 'common4']:
    url = 'https://%s.mptsweb.com/MBC/lassen/tax/search' % host
    try:
        r3 = s.get(url, timeout=5)
        print('%s: %d' % (url, r3.status_code))
        if r3.status_code == 200:
            print('  HIT! Response:', r3.text[:100])
    except Exception as e:
        print('%s: ERROR %s' % (url, str(e)[:60]))
