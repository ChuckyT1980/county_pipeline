"""Test enrichment on a small set of known-sold parcels."""
import csv
import sys
sys.path.insert(0, ".")
from butte_recorder_adapter import ButteRecorderAdapter

# Load sold parcels from 2024 that have owner names
sold = []
with open("butte_all_auction_parcels.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["status"] == "SOLD" and row["label"] in ("June 2024", "June 2026"):
            name = row.get("owner_name", "").strip()
            if name:
                sold.append(row)

print(f"Found {len(sold)} sold parcels with owner names in 2024/2026")

# Test a handful of owners
test = sold[:8]
test_names = list(set(r["owner_name"] for r in test))
print(f"Testing {len(test_names)} unique owners:\n")

adapter = ButteRecorderAdapter(headless=True)
adapter.start()

try:
    for name in test_names:
        search_key = name.split(",")[0].strip() if "," in name else name.split()[0].strip()
        events = adapter.name_search(search_key)
        deeds = [e for e in events if e["role"] == "TRANSFER"]
        print(f'{search_key} ({name[:50]}): {len(events)} total events, {len(deeds)} deeds')
        for d in deeds[:5]:
            print(f'  DOC {d["doc_number"]} {d["recorded_date"][:10]} | {d["grantor"][:50]} -> {d["grantee"][:50]}')
        print()
finally:
    adapter.close()

print("Done. Enrichment pipeline works." if len(test) > 0 else "No test parcels.")
