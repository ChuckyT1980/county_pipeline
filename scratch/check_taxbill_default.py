import requests
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

# Try the TaxBill Default.aspx (not RollCatCS)
url = 'https://apps.mptsweb.com/TaxBillv2/Default.aspx?County=shasta&Asmt=070050072000&TaxYear=2025&RollCat=SS&RollType=S'
resp = session.get(url, timeout=15)
print('Status:', resp.status_code)
soup = BeautifulSoup(resp.text, 'html.parser')
text = soup.get_text(separator='\n')
lines = [l.strip() for l in text.split('\n') if l.strip()]
print('=== All text ===')
for l in lines[:100]:
    print(l)

print()
print('=== Looking for owner/assessee ===')
for l in lines:
    if any(k in l.upper() for k in ['OWNER', 'ASSESSEE', 'NAME', 'TAXPAYER']):
        print(l)
