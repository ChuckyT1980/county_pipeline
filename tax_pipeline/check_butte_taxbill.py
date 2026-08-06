import requests
from bs4 import BeautifulSoup
import re

apn = "002271003000"
s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://common2.mptsweb.com/MBC/butte/tax/search',
})

# Try TaxBill on apps.mptsweb.com
url = (f"https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx"
       f"?CN=butte&Asmt={apn}&TaxYear=2025"
       f"&RollCat=CS&RollType=S&RollYear=")
print(f"Fetching TaxBill: {url}")
try:
    r = s.get(url, timeout=15)
    print(f"Status: {r.status_code}, Length: {len(r.text)}")
    soup = BeautifulSoup(r.text, "html.parser")
    full_text = soup.get_text(separator="\n")
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]
    # Look for all relevant data
    for line in lines:
        if any(x in line.lower() for x in ['owner', 'assessee', 'taxpayer', 'mail', 'name', 'location']):
            print(f"  {line[:120]}")
    # Show first 30 lines
    print(f"\nFirst 30 lines:")
    for line in lines[:30]:
        if line:
            print(f"  {line[:100]}")
except Exception as e:
    print(f"ERROR: {e}")
