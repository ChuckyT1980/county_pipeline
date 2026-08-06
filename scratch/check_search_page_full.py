"""Check the full search results page for embedded data"""
import requests, re, json
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'text/html, */*',
})

# First get the main page to build session
session.head('https://common2.mptsweb.com/MBC/shasta/tax/search', timeout=15)

# Now do a search by navigating to the search URL with a fee parcel
url = 'https://common2.mptsweb.com/MBC/shasta/tax/search/070050072'
resp = session.get(url, timeout=15)
html = resp.text

# Look for any data embedded in the page
soup = BeautifulSoup(html, 'html.parser')

# Find script tags with JSON or data
for s in soup.find_all('script'):
    txt = s.string or ''
    if txt.strip().startswith('{') or txt.strip().startswith('['):
        try:
            data = json.loads(txt)
            print('Found JSON data in script:')
            if isinstance(data, dict):
                print(list(data.keys())[:10])
            elif isinstance(data, list):
                print('Array of', len(data))
        except:
            pass
    if 'JResultsData' in txt:
        print('Found JResultsData script:')
        print(txt[:500])
        print('...')
        # Extract JSON from the sessionStorage reference
        match = re.search(r"JSON\.parse\(sessionStorage\.getItem\('([^']+)'\)\)", txt)
        if match:
            print('sessionStorage key:', match.group(1))
    if 'Row' in txt and ('Asmt' in txt or 'Owner' in txt or 'OwnerName' in txt):
        print('Script with Row/Asmt:', txt[:300])
