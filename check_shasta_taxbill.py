import requests, re, csv
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

apn = "070-050-072-000"
parcel = re.sub(r"[^0-9]", "", apn.strip())

# Try the TaxBill Default.aspx which shows the full bill
taxbill_url = f"https://apps.mptsweb.com/TaxBillv2/Default.aspx?County=shasta&Asmt={parcel}&TaxYear=2025&RollCat=CS&RollYr=&RollType=S"
print(f"TaxBill URL: {taxbill_url}")
resp = session.get(taxbill_url, timeout=15)
print(f"HTTP {resp.status_code} ({len(resp.text)} bytes)")

soup = BeautifulSoup(resp.text, "html.parser")
text = soup.get_text()
lines = [l.strip() for l in text.split('\n') if l.strip()]
print(f"\n=== Text content ({len(lines)} lines) ===")
for line in lines:
    if any(kw in line.lower() for kw in ['assessed', 'value', 'land', 'improvement', 'total', 'exemption', 'prop', 'tax', 'due', 'balance']):
        print(f"  {line[:150]}")

# Also try with DisplayType=HTML for a more parseable version
url2 = taxbill_url + "&DisplayType=HTML"
resp2 = session.get(url2, timeout=15)
soup2 = BeautifulSoup(resp2.text, "html.parser")
text2 = soup2.get_text()
lines2 = [l.strip() for l in text2.split('\n') if l.strip()]
print(f"\n=== HTML version ({len(lines2)} lines) ===")
for line in lines2:
    if any(kw in line.lower() for kw in ['assessed', 'value', 'land', 'improvement', 'total', 'exemption', 'prop', 'tax', 'due', 'balance']):
        print(f"  {line[:150]}")

# Also try Shasta county assessor portal
print("\n=== Trying Shasta County Assessor ===")
assessor_url = f"https://www.co.shasta.ca.us/assessor/property-search"
r3 = session.get(assessor_url, timeout=15)
print(f"Assessor search: HTTP {r3.status_code} ({len(r3.text)} bytes)")
if r3.status_code == 200:
    # Look for search form
    s3 = BeautifulSoup(r3.text, "html.parser")
    for form in s3.find_all('form'):
        action = form.get('action', '')
        print(f"  Form action: {action}")
