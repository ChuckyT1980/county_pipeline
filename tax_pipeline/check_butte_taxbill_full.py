import requests
from bs4 import BeautifulSoup
import re

apn = "002271003000"
s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://common2.mptsweb.com/MBC/butte/tax/search',
})

url = (f"https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx"
       f"?CN=butte&Asmt={apn}&TaxYear=2025"
       f"&RollCat=CS&RollType=S&RollYear=")
r = s.get(url, timeout=15)
soup = BeautifulSoup(r.text, "html.parser")
full_text = soup.get_text(separator="\n")
lines = [l.strip() for l in full_text.split("\n") if l.strip()]

# Print ALL lines to see full structure
print("=== ALL CONTENT ===")
for i, line in enumerate(lines):
    print(f"{i:3d}: {line[:120]}")
