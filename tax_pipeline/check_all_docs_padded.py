import requests, csv, time, concurrent.futures
from bs4 import BeautifulSoup

raw_apns = []
with open(r'C:\Users\chuck\Downloads\county_pipeline\archive\butte_MASTER_leads_with_liens.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        raw_apns.append(row['asmt'].strip())

# Zero-pad all APNs to 12 digits
apns = [a.zfill(12) for a in raw_apns]
print(f"Total: {len(apns)}")
print(f"Sample raw->padded: {[(r, a) for r, a in zip(raw_apns[:5], apns[:5])]}")

def check_doc(apn):
    try:
        s = requests.Session()
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://common1.mptsweb.com/mbap/butte/asr',
        })
        r = s.get(f"https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/{apn}", timeout=15)
        if r.status_code != 200:
            return (apn, None, f"HTTP_{r.status_code}")
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if "Current Document Number" in label:
                    return (apn, value.strip() if value else None, "OK")
        return (apn, None, "NO_ROW")
    except Exception as e:
        return (apn, None, str(e)[:50])

results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    fut = {ex.submit(check_doc, apn): apn for apn in apns}
    for i, f in enumerate(concurrent.futures.as_completed(fut)):
        results.append(f.result())
        if (i+1) % 50 == 0:
            print(f"Progress: {i+1}/{len(apns)}")

has_doc = sum(1 for r in results if r[1])
no_doc = sum(1 for r in results if not r[1])
print(f"\nWith doc: {has_doc}, without: {no_doc}")

# Check doc type prefix letters  
prefixes = {}
for r in results:
    if r[1]:
        p = r[1][4:5]  # letter after year
        prefixes[p] = prefixes.get(p, 0) + 1
print(f"Doc type prefixes: {prefixes}")

# Sample
print(f"\nSample docs:")
for r in results[:10]:
    if r[1]:
        doc = r[1]
        rec_fmt = doc[:4] + "-" + doc[5:]  # 2024R0030607 -> 2024-0030607
        print(f"  {r[0]}: {doc} -> {rec_fmt}")
