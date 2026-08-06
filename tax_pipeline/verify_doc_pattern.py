import requests, csv, re, random
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

# Read the MASTER CSV to get APNs
apns = []
with open(r'C:\Users\chuck\Downloads\county_pipeline\archive\butte_MASTER_leads_with_liens.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        apns.append(row['asmt'])

print(f"Total APNs: {len(apns)}")

# Test doc_number format across a sample
sample = random.sample(apns, min(20, len(apns)))
print(f"\nTesting {len(sample)} APNs for doc_number pattern...")
patterns = {}
for apn in sample:
    try:
        compact = apn.replace("-", "").strip()
        r = s.get(f"https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/{compact}", timeout=10)
        if r.status_code != 200:
            print(f"  {apn} -> HTTP {r.status_code}")
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        doc_num = None
        prop_type = None
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if "Current Document Number" in label:
                    doc_num = value
                if "Property Type" in label:
                    prop_type = value
        if doc_num:
            # Extract pattern
            pattern = re.sub(r'\d', 'N', doc_num)
            pattern = re.sub(r'[A-Z]', 'L', pattern)
            patterns[pattern] = patterns.get(pattern, 0) + 1
            print(f"  {apn} -> doc={doc_num} type={prop_type}")
        else:
            print(f"  {apn} -> NO DOC NUMBER")
    except Exception as e:
        print(f"  {apn} -> ERROR: {e}")

print(f"\nPatterns found: {patterns}")
