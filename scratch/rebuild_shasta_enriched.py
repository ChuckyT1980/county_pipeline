"""Rebuild shasta enriched CSV with recorder owner names"""
import csv, json, os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load doc search results
doc_results = json.load(open(os.path.join(base_dir, 'scratch/shasta_doc_search_results.json')))

# Build APN -> grantee mapping
apn_to_grantee = {}
for r in doc_results:
    apn_to_grantee[r['apn']] = r['grantee']

# Load the export CSV
export_path = os.path.join(base_dir, 'northern_ca_MASTER_export.csv')
rows = []
with open(export_path) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        row = dict(row)
        apn = row.get('apn', '').strip()
        fee = row.get('fee_parcel', '').strip()
        
        # Try to find grantee by fee_parcel first (since doc_data keys are fee_parcels)
        grantee = apn_to_grantee.get(fee, '')
        if not grantee:
            grantee = apn_to_grantee.get(apn, '')
        
        if grantee:
            # The Grantee on the most recent deed is the current owner
            row['owner_name'] = grantee
            row['recorder_info'] = f'Recorder: most recent deed grantee = {grantee}'
            row['notes'] = f'Owner from Shasta Recorder document search. Liens not checked.'
        
        rows.append(row)

# Write updated CSV
output_path = os.path.join(base_dir, 'northern_ca_MASTER_export_with_owners.csv')
with open(output_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Written {len(rows)} rows to {output_path}")

# Summary
shasta_rows = [r for r in rows if r.get('county', '').lower() == 'shasta']
tehama_rows = [r for r in rows if r.get('county', '').lower() == 'tehama']
shasta_with_owner = [r for r in shasta_rows if r.get('owner_name', '') and r['owner_name'] != 'SKIP_TRACE_REQUIRED']
tehama_with_owner = [r for r in tehama_rows if r.get('owner_name', '') and r['owner_name'] != 'SKIP_TRACE_REQUIRED']

print(f"\nShasta: {len(shasta_rows)} rows, {len(shasta_with_owner)} with owner names")
for r in shasta_with_owner:
    print(f"  {r['apn']:20s} Owner={r['owner_name'][:40]:40s} Balance={r['total_balance']:>10s}")

print(f"\nTehama: {len(tehama_rows)} rows, {len(tehama_with_owner)} with owner names")

# Also count empty owner names in Shasta
shasta_no_owner = [r for r in shasta_rows if not r.get('owner_name', '') or r['owner_name'] == 'SKIP_TRACE_REQUIRED']
print(f"\nShasta without owner: {len(shasta_no_owner)}")
for r in shasta_no_owner:
    print(f"  {r['apn']:20s} fee={r['fee_parcel']:20s}")
