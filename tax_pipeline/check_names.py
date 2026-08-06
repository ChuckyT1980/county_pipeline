import csv

path = r"C:\Users\chuck\Downloads\county_pipeline\archive\leads_for_sale.csv"
with open(path) as f:
    rows = list(csv.DictReader(f))

print(f"Total: {len(rows)} rows")
print(f"Columns: {list(rows[0].keys())}")

missing_first = sum(1 for r in rows if not r.get("FirstName","").strip())
missing_last = sum(1 for r in rows if not r.get("LastName","").strip())
missing_full = sum(1 for r in rows if not r.get("FullName","").strip())
print(f"\nMissing FirstName: {missing_first}/{len(rows)}")
print(f"Missing LastName:  {missing_last}/{len(rows)}")
print(f"Missing FullName:  {missing_full}/{len(rows)}")

print("\nSamples of rows with missing FirstName:")
count = 0
for r in rows:
    if not r.get("FirstName","").strip():
        print(f"  FullName={r.get('FullName','')!r}  LastName={r.get('LastName','')!r}  APN={r.get('APN','')}")
        count += 1
        if count >= 10:
            break

print("\nSamples of rows WITH FirstName:")
count = 0
for r in rows:
    if r.get("FirstName","").strip():
        print(f"  First={r.get('FirstName','')!r} Last={r.get('LastName','')!r} Full={r.get('FullName','')!r}")
        count += 1
        if count >= 5:
            break

print("\nFullName format analysis...")
from collections import Counter
patterns = Counter()
import re
for r in rows:
    fn = r.get("FullName","").strip()
    if not fn:
        patterns["(empty)"] += 1
    elif "," in fn:
        patterns["LAST, FIRST"] += 1
    elif " & " in fn:
        patterns["FIRST & FIRST"] += 1
    else:
        patterns["other"] += 1
for p, c in patterns.most_common():
    print(f"  {p}: {c}")
