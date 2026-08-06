import requests, re, csv
from bs4 import BeautifulSoup

def normalize_parcel(raw):
    return re.sub(r"[^0-9]", "", raw.strip())

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

s = list(csv.DictReader(open('tax_pipeline/shasta_MASTER_leads_with_liens.csv', newline='', encoding='utf-8-sig')))

for r in s[:3]:
    apn = r['APN']
    parcel = normalize_parcel(apn)
    tax_url = f"https://common2.mptsweb.com/MBC/shasta/tax/main/{parcel}/2025/0000"
    
    resp = session.get(tax_url, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    
    print(f"\n=== {apn} ===")
    
    # Find the assessment table - look for INS | Assessment | Amount
    table = soup.find('table')
    if table:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td','th'])
            row_text = ' | '.join(c.get_text(strip=True) for c in cells)
            print(f"  {row_text}")
    
    # Also look for situs address / property info
    text = soup.get_text()
    for line in text.split('\n'):
        line = line.strip()
        if line and any(kw in line.lower() for kw in ['situs', 'property', 'parcel', 'owner', 'mailing']):
            print(f"  INFO: {line[:150]}")

print("\n--- Trying to extract assessed values from all Shasta leads ---")
results = []
for r in s:
    apn = r['APN']
    parcel = normalize_parcel(apn)
    tax_url = f"https://common2.mptsweb.com/MBC/shasta/tax/main/{parcel}/2025/0000"
    try:
        resp = session.get(tax_url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find('table')
        assessed = ""
        if table:
            for row in table.find_all('tr'):
                cells = row.find_all(['td','th'])
                if len(cells) >= 3:
                    label = cells[0].get_text(strip=True)
                    desc = cells[1].get_text(strip=True)
                    amount = cells[2].get_text(strip=True)
                    if 'assessed' in label.lower():
                        assessed = amount
        results.append({'apn': apn, 'assessed': assessed})
    except Exception as e:
        results.append({'apn': apn, 'assessed': f'ERROR: {e}'})

found = sum(1 for r in results if r['assessed'] and not r['assessed'].startswith('ERROR'))
print(f"Assessed values found: {found}/{len(results)}")
for r in results[:5]:
    print(f"  {r['apn']}: {r['assessed']}")
