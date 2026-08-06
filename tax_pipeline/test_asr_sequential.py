import requests, csv, time, concurrent.futures
from bs4 import BeautifulSoup

apns = []
with open(r'C:\Users\chuck\Downloads\county_pipeline\archive\butte_MASTER_leads_with_liens.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        apns.append(row['asmt'].strip())

print(f"Total: {len(apns)}")
print(f"Sample APNs: {apns[:5]}")

def check_doc(apn):
    try:
        compact = apn.replace("-", "").strip()
        s = requests.Session()
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://common1.mptsweb.com/mbap/butte/asr',
        })
        url = f"https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/{compact}"
        r = s.get(url, timeout=15)
        if r.status_code != 200:
            return (apn, None, f"HTTP_{r.status_code}")
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if "Current Document Number" in label:
                    return (apn, value.strip() if value else None, "OK_EMPTY" if not value.strip() else "OK")
        return (apn, None, "NO_ROW")
    except Exception as e:
        return (apn, None, str(e)[:50])

# Test non-concurrent first
print("\n=== Sequential test (first 10) ===")
for apn in apns[:10]:
    result = check_doc(apn)
    print(f"  {result[0]} -> {result[1]} ({result[2]})")
