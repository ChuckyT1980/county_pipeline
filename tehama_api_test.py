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

# Step 1: establish session
session.get(BASE + "/tehama/tax/search")

def fetch(field, query):
    url = f"{BASE}/api/search/tehama/0000-CURR/{field}/{query}"
    r = session.get(url, headers=headers)
    print(f"[{r.status_code}] {url} - length: {len(r.text)}")
    if r.status_code == 200:
        return r.json()
    return None

test_queries = [
    {"field": "situs", "query": "A"}
]

results = []

for item in test_queries:
    field = item["field"]
    q = item["query"]
    data = fetch(field, q)
    if data:
        results.append({
            "query": q,
            "field": field,
            "data": data
        })
    time.sleep(0.3)

with open("tehama_live_test.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"Captured {len(results)} result sets")
