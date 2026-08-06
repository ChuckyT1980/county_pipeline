"""Try alternative endpoints for owner data."""
import requests, json

apn = "035470012000"
headers = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
base = "https://common1.mptsweb.com/MBC"
slug = "tehama"

# Variants of owner endpoint
endpoints = [
    (f"{base}/api/search/{slug}/0000-CURR/owner/{apn[:11]}", "owner full"),
    (f"{base}/api/search/{slug}/0000-CURR/ownername/{apn[:11]}", "ownername"),
    (f"{base}/api/search/{slug}/0000-CURR/taxpayer/{apn[:11]}", "taxpayer"),
    (f"{base}/api/search/{slug}/0000-CURR/assessee/{apn[:11]}", "assessee"),
]

for url, name in endpoints:
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code == 200 and len(r.text) > 50:
        try:
            data = r.json()
            if isinstance(data, str):
                data = json.loads(data)
            print(f"[200] {name:<20} {json.dumps(data, indent=2)[:300]}")
        except:
            print(f"[200] {name:<20} raw: {r.text[:200]}")
    else:
        print(f"[{r.status_code}] {name}")

# Also check if the old discovery CSV has owner names (it was from address search)
import pandas as pd
df = pd.read_csv("tehama_discovery_20260627_004437.csv")
print(f"\nDiscovery CSV columns: {list(df.columns)}")
# Check if owner info is in any detail_url page from before maintenance
# The discovery CSV doesn't have owner column — it only has asmt, address, tra, roll_cat
