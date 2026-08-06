import csv

with open("butte_all_auction_parcels.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

no_owner = [r for r in rows if not r["owner_name"].strip()]
has_owner = [r for r in rows if r["owner_name"].strip()]
print(f"Total: {len(rows)}")
print(f"Without owner name: {len(no_owner)}")
print(f"With owner name: {len(has_owner)}")

# Show which years have no owners
from collections import Counter
by_year = Counter()
for r in no_owner:
    by_year[r["label"]] += 1
print("\nParcels without owner by auction:")
for k, v in sorted(by_year.items()):
    print(f"  {k}: {v}")

# Show status breakdown
status_counts = Counter()
for r in rows:
    status_counts[r["status"] if r["status"] else "UNKNOWN"] += 1
print("\nStatus breakdown:")
for k, v in sorted(status_counts.items()):
    print(f"  {k}: {v}")
