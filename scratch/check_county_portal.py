"""Check Shasta County's own property portal for owner data"""
import requests
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

# Try the MBC Inquiry link
url = 'https://www.co.shasta.ca.us/index/tc_index/mbinquiry.aspx'
resp = session.get(url, timeout=15)
print('Status:', resp.status_code)
print('Content-Type:', resp.headers.get('Content-Type'))
soup = BeautifulSoup(resp.text, 'html.parser')
text = soup.get_text(separator='\n')
lines = [l.strip() for l in text.split('\n') if l.strip()]
print('=== First 60 lines ===')
for l in lines[:60]:
    print(l)

print()
print('=== Search-related ===')
for l in lines:
    if any(k in l.upper() for k in ['SEARCH', 'PARCEL', 'APN', 'PROPERTY', 'INQUIRY', 'ASSESSMENT', 'OWNER']):
        print(l[:200])
