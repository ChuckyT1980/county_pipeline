"""Check MBC page JS for API endpoints that might have owner data"""
import requests, re, json
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

url = 'https://common2.mptsweb.com/MBC/shasta/tax/main/070050072000/2025/0000'
resp = session.get(url, timeout=15)
soup = BeautifulSoup(resp.text, 'html.parser')

# Find ALL scripts
scripts = soup.find_all('script')
for i, s in enumerate(scripts):
    txt = s.string or ''
    if not txt:
        continue
    # Look for API URLs, AJAX calls, data loading patterns
    matches = re.findall(r'(https?://[^"\'\s]+(?:api|Ajax|Load|Get|Fetch|Data)[^"\'\s]*)', txt, re.I)
    for m in matches:
        print('Script %d API URL: %s' % (i, m))
    
    # Look for URL patterns in general
    urls = re.findall(r'["\'](https?://[^"\'\s]+)["\']', txt)
    for u in urls:
        if 'api' in u.lower() or 'ajax' in u.lower() or 'data' in u.lower() or 'search' in u.lower() or 'detail' in u.lower():
            print('  URL: %s' % u)

print('\n=== Looking for data attributes with URLs ===')
for tag in soup.find_all(True):
    for attr in tag.attrs:
        val = str(tag[attr])
        if 'api' in val.lower() or 'ajax' in val.lower() or '/tax/' in val.lower() or '/detail' in val.lower():
            print('  %s[%s] = %s' % (tag.name, attr, val[:150]))
