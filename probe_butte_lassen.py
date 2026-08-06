import requests, json

s = requests.Session()
s.headers['User-Agent'] = 'Mozilla/5.0'
s.headers['X-Requested-With'] = 'XMLHttpRequest'
s.headers['Accept'] = 'application/json, text/javascript, */*'

for prefix in ['001000','002000','010000','100000','200000','300000']:
    r = s.get('https://common1.mptsweb.com/MBC/api/search/butte/0000-CURR/feeparcel/%s' % prefix, timeout=10)
    try:
        data = json.loads(json.loads(r.text)) if r.text.startswith('"') else r.json()
        rows = data.get('Table',{}).get('Row',[])
        if isinstance(rows, dict): rows = [rows]
        real = [rw for rw in rows if rw.get('Asmt')]
        if real:
            print('Butte HIT prefix=%s: %d rows, sample=%s' % (prefix, len(real), real[0]))
        else:
            print('Butte EMPTY prefix=%s' % prefix)
    except Exception as e:
        print('Butte ERROR prefix=%s: %s' % (prefix, str(e)[:60]))

# Check Shasta Tyler search URL - the Shasta recorder config has wrong URL
print()
print('Shasta Tyler URL check:')
for url in [
    'https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S4',
    'https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1',
]:
    try:
        r = s.get(url, timeout=8)
        print('%s -> %d' % (url, r.status_code))
    except Exception as e:
        print('%s -> ERROR: %s' % (url, str(e)[:50]))
