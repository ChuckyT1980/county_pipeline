import requests, json

s = requests.Session()
s.headers['User-Agent'] = 'Mozilla/5.0'
s.headers['X-Requested-With'] = 'XMLHttpRequest'
s.headers['Accept'] = 'application/json, text/javascript, */*'

# Butte APNs found in search: 039-040-017, 040-200-098
print("Testing Butte prefixes based on actual APN formats found...")
for prefix in ['039000','039040','040000','040200','039','040']:
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

print("\nTesting Lassen CountyTaxRetriever...")
try:
    r = s.get('https://www.countytaxretriever.com', timeout=10)
    print("CountyTaxRetriever Status:", r.status_code)
    print("Title:", r.text.split('<title>')[1].split('</title>')[0] if '<title>' in r.text else 'No title')
except Exception as e:
    print("CountyTaxRetriever ERROR:", e)
