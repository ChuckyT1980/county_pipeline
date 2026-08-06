"""Check Tehama data gap: which export rows lack owner names?"""
import csv, os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Check export
export_path = os.path.join(base_dir, 'northern_ca_MASTER_export.csv')
with open(export_path) as f:
    reader = csv.DictReader(f)
    print("Export Tehama rows:")
    for row in reader:
        if row.get('county', '').lower() == 'tehama':
            fee = row.get('fee_parcel', '').strip()
            owner = row.get('owner_name', '').strip()
            apn = row.get('apn', '').strip()
            print(f"  fee={fee:20s} apn={apn:20s} owner={owner:30s}")

# Check enriched file to see assessee_name for those fee parcels
print("\n\nChecking enriched file for those fee parcels...")
enriched_path = os.path.join(base_dir, 'tax_pipeline/tehama_MASTER_leads_enriched.csv')
target_fees = ['60050021000.0', '6320006000.0', '100140007000.0']
with open(enriched_path) as f:
    reader = csv.DictReader(f)
    found = 0
    for row in reader:
        fee = row.get('fee_parcel', '').strip()
        if fee in target_fees:
            found += 1
            print(f"  fee={fee:20s} owner_name={row.get('owner_name',''):30s} assessee_name={row.get('assessee_name',''):30s} source={row.get('source',''):20s}")
    print(f"  Found {found}/{len(target_fees)} target fees")

# Count how many export Tehama rows are missing owner
print("\n\nCounting all export Tehama rows missing owner...")
count_tehama = 0
count_no_owner = 0
with open(export_path) as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row.get('county', '').lower() == 'tehama':
            count_tehama += 1
            if not row.get('owner_name', '').strip() or row['owner_name'].strip() == 'SKIP_TRACE_REQUIRED':
                count_no_owner += 1
print(f"  Tehama rows in export: {count_tehama}")
print(f"  Missing owner: {count_no_owner}")

# Now find the assessee_name for the unenriched Tehama rows
print("\n\nFinding assessee_name for unenriched Tehama rows...")
with open(export_path) as f:
    export_rows = list(csv.DictReader(f))

tehama_missing = []
for row in export_rows:
    if row.get('county', '').lower() == 'tehama':
        owner = row.get('owner_name', '').strip()
        if not owner or owner == 'SKIP_TRACE_REQUIRED':
            fee = row.get('fee_parcel', '').strip()
            tehama_missing.append(fee)

# Look up in enriched
with open(enriched_path) as f:
    enriched_rows = list(csv.DictReader(f))

for fee in tehama_missing:
    found = False
    for er in enriched_rows:
        if er.get('fee_parcel', '').strip() == fee:
            print(f"  fee={fee:20s} assessee={er.get('assessee_name','?'):30s} owner_name={er.get('owner_name','?'):30s} source={er.get('source','?'):20s}")
            found = True
            break
    if not found:
        print(f"  fee={fee:20s} NOT FOUND in enriched")
