import requests
import json
import time

BASE = "https://common1.mptsweb.com/MBC"
session = requests.Session()
headers = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
    "Referer": BASE + "/tehama/tax/search"
}

session.get(BASE + "/tehama/tax/search")

def fetch(field, query):
    url = f"{BASE}/api/search/tehama/0000-CURR/{field}/{query}"
    r = session.get(url, headers=headers)
    if r.status_code == 200:
        return r.json()
    return None

seed_queries = [
    "1 Main", "2 Main", "3 Main", "4 Main", "5 Main",
    "1 Oak", "2 Oak", "1 Pine", "2 Pine", "1 Cedar",
    "A", "B", "C", "Corning", "Red Bluff", "Los Molinos",
    "1st", "2nd", "3rd", "4th", "5th"
]

all_apns = set()

for q in seed_queries:
    data = fetch("situs", q)
    if data:
        try:
            if isinstance(data, str):
                data = json.loads(data)
            rows = data.get("Table", {}).get("Row", [])
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows:
                apn = row.get("FeeParcel") or row.get("Asmt")
                if apn:
                    apn = apn.replace("-", "").strip()
                    all_apns.add(apn)
        except:
            pass

prefixes_6 = set()
for apn in all_apns:
    if len(apn) >= 6:
        prefixes_6.add(f"{apn[:3]}-{apn[3:6]}")

sorted_prefixes_6 = sorted(list(prefixes_6))
print(f"6-digit seeds: {sorted_prefixes_6}")

with open("tehama_seed_prefixes_6.json", "w") as f:
    json.dump(sorted_prefixes_6, f)
