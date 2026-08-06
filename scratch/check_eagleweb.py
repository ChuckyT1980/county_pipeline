import requests
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

# Get the Shasta EagleWeb search page
url = 'https://recorderselfservice.shastacounty.gov/web/search/DOCSEARCH4S1'
resp = session.get(url, timeout=15)
print('Status:', resp.status_code)
soup = BeautifulSoup(resp.text, 'html.parser')

# Look for search fields, forms, and instructions
forms = soup.find_all('form')
for f in forms:
    action = f.get('action', '')
    print('\nForm action:', action)
    for inp in f.find_all(['input', 'select', 'textarea', 'button']):
        name = inp.get('name', '')
        id_ = inp.get('id', '')
        typ = inp.get('type', '')
        placeholder = inp.get('placeholder', '')
        label_text = ''
        # Find associated label
        if id_:
            label = soup.find('label', attrs={'for': id_})
            if label:
                label_text = label.get_text(strip=True)
        if name or id_:
            print('  name=%-20s id=%-20s type=%-10s placeholder=%-20s label=%s' % 
                  (name[:20], id_[:20], typ[:10], placeholder[:20], label_text[:30]))

# Print all text to find APN/parcel search instructions
text = soup.get_text(separator='\n')
lines = [l.strip() for l in text.split('\n') if l.strip()]
print('\n=== Search-related text ===')
for l in lines:
    if any(k in l.upper() for k in ['SEARCH', 'PARCEL', 'APN', 'DOCUMENT', 'NAME', 'INSTRUCTION', 'HELP', 'FIND']):
        print(l[:200])
