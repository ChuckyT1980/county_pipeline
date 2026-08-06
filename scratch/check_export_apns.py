"""Check export APNs vs doc numbers"""
import csv, json

# Load doc numbers
doc_data = json.load(open('scratch/shasta_export_doc_numbers.json'))

# Load export
with open('northern_ca_MASTER_export.csv') as f:
    reader = csv.DictReader(f)
    export_apns = []
    for row in reader:
        apn = row.get('apn', '').strip()
        bal = row.get('total_balance', '?')
        owner = row.get('owner_name', '?')[:30]
        county = row.get('county', '?')
        fee = row.get('fee_parcel', '')
        print(f"apn={apn:20s} fee={fee:20s} Owner={owner:30s} Balance={bal:>10s}")
        export_apns.append(apn)

print(f"\nTotal export rows: {len(export_apns)}")
print(f"Doc data APNs: {list(doc_data.keys())}")

# Find which export APNs have doc numbers
print("\n=== Doc number matches ===")
for apn in export_apns:
    if apn in doc_data:
        print(f"  {apn}: doc={doc_data[apn]}")
    elif apn.replace('-', '') in doc_data or apn in doc_data.values():
        print(f"  {apn}: found as fee_parcel key")
    else:
        print(f"  {apn}: NO DOC NUMBER")

