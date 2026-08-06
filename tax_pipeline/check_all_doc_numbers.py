import requests, csv, time
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

# Read ALL APNs from MASTER CSV
apns = []
with open(r'C:\Users\chuck\Downloads\county_pipeline\archive\butte_MASTER_leads_with_liens.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        apns.append(row['asmt'])

print(f"Total APNs: {len(apns)}")

# Check doc_number availability
has_doc = 0
no_doc = 0
doc_formats = {}
for i, apn in enumerate(apns):
    try:
        compact = apn.replace("-", "").strip()
        r = s.get(f"https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/{compact}", timeout=10)
        if r.status_code != 200:
            no_doc += 1
            continue
        
        soup = BeautifulSoup(r.text, "html.parser")
        doc_num = None
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if "Current Document Number" in label and value:
                    doc_num = value
                    break
        
        if doc_num:
            has_doc += 1
            fmt = type(doc_num).__name__ + ":" + doc_num[:15]
            doc_formats[fmt] = doc_formats.get(fmt, 0) + 1
        else:
            no_doc += 1
        
        if (i+1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(apns)} (has_doc: {has_doc}, no_doc: {no_doc})")
        time.sleep(0.25)
        
    except Exception as e:
        no_doc += 1
        if (i+1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(apns)} error: {e}")

print(f"\nResults: {has_doc} with doc_number, {no_doc} without")
print(f"Format samples: {list(doc_formats.keys())[:10]}")
