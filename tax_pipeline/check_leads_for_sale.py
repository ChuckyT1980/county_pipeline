import csv, os

path = r"C:\Users\chuck\Downloads\county_pipeline\leads_for_sale.csv"
with open(path) as f:
    rows = list(csv.DictReader(f))

print("Total rows:", len(rows))
if not rows:
    exit()

k = list(rows[0].keys())
print("Columns:", k)

missing_first = sum(1 for r in rows if not r.get("FirstName","").strip())
missing_last = sum(1 for r in rows if not r.get("LastName","").strip())
missing_full = sum(1 for r in rows if not r.get("FullName","").strip())
missing_apn = sum(1 for r in rows if not r.get("APN","").strip())

print(f"Missing FirstName: {missing_first}/{len(rows)}")
print(f"Missing LastName:  {missing_last}/{len(rows)}")
print(f"Missing FullName:  {missing_full}/{len(rows)}")
print(f"Missing APN:       {missing_apn}/{len(rows)}")

print("\nFirst 8 rows:")
for r in rows[:8]:
    print(f"  First={r.get('FirstName','')!r} Last={r.get('LastName','')!r} APN={r.get('APN','')} County={r.get('County','')}")
