import csv, json, os

base = r"C:\Users\chuck\Downloads\county_pipeline\tax_pipeline"
parent = r"C:\Users\chuck\Downloads\county_pipeline"

# 1. Check sample discovery file (enriched data)
sd = os.path.join(base, "butte_sample_discovery_20260707_185258.csv")
if os.path.exists(sd):
    with open(sd) as f:
        r = csv.DictReader(f)
        rows = list(r)
    print(f"Sample discovery: {len(rows)} rows")
    if rows:
        k = list(rows[0].keys())
        print(f"  cols ({len(k)}): {k}")
        # show signal/data columns (skip basic ones)
        for row in rows[:2]:
            for col, val in row.items():
                if val and val not in ("0", "False", ""):
                    print(f"    {col} = {val}")
            print("  ---")

# 2. Check CRM enriched
crm = os.path.join(parent, "butte_crm_20260707_185600_enriched.csv")
if os.path.exists(crm):
    with open(crm) as f:
        r = csv.DictReader(f)
        rows = list(r)
    print(f"CRM enriched: {len(rows)} rows")
    if rows:
        k = list(rows[0].keys())
        print(f"  cols ({len(k)}): {k}")
        for row in rows[:1]:
            for col, val in row.items():
                if val and val not in ("0", "False", ""):
                    print(f"    {col} = {val}")

# 3. What market/sales data do we have anywhere?
print("\n--- Any sales data? ---")
all_files = []
for d in [base, parent]:
    for f in os.listdir(d):
        if any(x in f.lower() for x in ["sale", "market", "value", "price", "grant", "deed"]):
            all_files.append(os.path.join(d, f))
if all_files:
    for f in all_files:
        print(f"  {os.path.basename(f)} ({os.path.getsize(f)/1024:.0f}KB)")
else:
    print("  None found")

# 4. Look for any enriched/enrichment files
print("\n--- Enrichment/signal files ---")
for d in [base, parent]:
    for f in os.listdir(d):
        if any(x in f.lower() for x in ["enrich", "signal", "distress", "lien", "score", "intent"]):
            fp = os.path.join(d, f)
            print(f"  {os.path.basename(fp)} ({os.path.getsize(fp)/1024:.0f}KB)")
