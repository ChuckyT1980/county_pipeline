"""Search raw MBC HTML for any owner-related data"""
import requests
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

url = 'https://common2.mptsweb.com/MBC/shasta/tax/main/070050072000/2025/0000'
resp = session.get(url, timeout=15)
html = resp.text

# Search for owner/name/assessee in the raw HTML
import re
for keyword in ['owner', 'assessee', 'taxpayer', 'party', 'grantee', 'grantor', 'GSTEIGER', '- STEIGER', 'STEIGER', 'DANIEL']:
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    for m in pattern.finditer(html):
        start = max(0, m.start() - 100)
        end = min(len(html), m.end() + 100)
        context = html[start:end]
        print('Found "%s" at %d: ...%s...' % (keyword, m.start(), context[:200]))
        print()

# Check for any JSON-like data structures
print('\n=== Looking for JSON data ===')
json_matches = re.findall(r'\{[^{}]*?"[^"]*?"[^{}]*?\}', html)
for j in json_matches[:20]:
    if any(k in j.lower() for k in ['owner', 'name', 'assess', 'party', 'person', 'mail']):
        print(j[:300])
        print()

# Check for hidden inputs with owner data
soup = BeautifulSoup(html, 'html.parser')
hidden = soup.find_all('input', type='hidden')
for h in hidden:
    name = h.get('name', '')
    val = h.get('value', '')
    if val and any(k in (name + val).lower() for k in ['owner', 'name', 'assess', 'party']):
        print('Hidden: %s = %s' % (name, val[:100]))

# Check meta tags
for meta in soup.find_all('meta'):
    name = meta.get('name', '')
    content = meta.get('content', '')
    if content and any(k in content.lower() for k in ['owner', 'name']):
        print('Meta: %s = %s' % (name, content[:100]))

# Check if there's a JSON+LD script
for script in soup.find_all('script', type='application/ld+json'):
    print('JSON-LD:', script.string[:500])
