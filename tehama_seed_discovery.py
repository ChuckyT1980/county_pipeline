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

# Broad situs queries to hit a large cross-section of the county
seed_queries = [
    "1 Main", "2 Main", "3 Main", "4 Main", "5 Main",
    "1 Oak", "2 Oak", "1 Pine", "2 Pine", "1 Cedar",
    "A", "B", "C", "Corning", "Red Bluff", "Los Molinos",
    "1st", "2nd", "3rd", "4th", "5th"
]

all_apns = set()

print("Starting seed discovery...")
for q in seed_queries:
    data = fetch("situs", q)
    if data:
        try:
            if isinstance(data, str):
                data = json.loads(data)
            rows = data.get("Table", {}).get("Row", [])
            if isinstance(rows, dict):
                rows = [rows]
            count = 0
            for row in rows:
                apn = row.get("FeeParcel") or row.get("Asmt")
                if apn:
                    apn = apn.replace("-", "").strip()
                    all_apns.add(apn)
                    count += 1
            print(f"Query '{q}': {count} APNs found")
        except Exception as e:
            print(f"Query '{q}': JSON parsing error: {e}")
    else:
        print(f"Query '{q}': 0 results or 404")
    time.sleep(0.3)

# Extract first 3 digits (typical Book identifier in CA APNs)
prefixes = set()
for apn in all_apns:
    if len(apn) >= 3:
        prefixes.add(apn[:3])

sorted_prefixes = sorted(list(prefixes))

print(f"\nTotal unique APNs discovered: {len(all_apns)}")
print(f"Total unique 3-digit prefixes (Books): {len(sorted_prefixes)}")
print(f"Prefixes:\n{json.dumps(sorted_prefixes)}")

with open("tehama_seed_prefixes.json", "w") as f:
    json.dump(sorted_prefixes, f, indent=2)
