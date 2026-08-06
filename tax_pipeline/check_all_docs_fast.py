import requests, csv, time, concurrent.futures
from bs4 import BeautifulSoup

apns = []
with open(r'C:\Users\chuck\Downloads\county_pipeline\archive\butte_MASTER_leads_with_liens.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        apns.append(row['asmt'])

def check_doc(apn):
    try:
        compact = apn.replace("-", "").strip()
        s = requests.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0'})
        r = s.get(f"https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/{compact}", timeout=15)
        if r.status_code != 200:
            return (apn, None, f"HTTP_{r.status_code}")
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if "Current Document Number" in label and value:
                    return (apn, value, "OK")
        return (apn, None, "EMPTY")
    except Exception as e:
        return (apn, None, str(e)[:30])

results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    fut = {ex.submit(check_doc, apn): apn for apn in apns}
    for i, f in enumerate(concurrent.futures.as_completed(fut)):
        results.append(f.result())
        if (i+1) % 50 == 0:
            print(f"Progress: {i+1}/{len(apns)}")

has_doc = sum(1 for r in results if r[1])
no_doc = sum(1 for r in results if not r[1])
print(f"\nTotal: {len(results)}, with doc: {has_doc}, without: {no_doc}")

# Count formats
formats = {}
for r in results:
    if r[1]:
        f = r[1][:4] + "-" + r[1][5:-4] + "..."  # format: YYYY-L-NNNNNNN
        formats[r[1][4:5]] = formats.get(r[1][4:5], 0) + 1  # group by type letter
print(f"Doc type letters: {formats}")
# Show first/last few
has_list = [r for r in results if r[1]]
print(f"Sample docs:")
for r in has_list[:5]:
    doc = r[1]
    recorder_fmt = doc[:4] + "-" + doc[5:]
    print(f"  {r[0]}: {doc} -> {recorder_fmt}")
# Save the results
with open("doc_numbers_results.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["asmt", "doc_number", "status"])
    w.writerows(results)
print("\nSaved to doc_numbers_results.csv")
