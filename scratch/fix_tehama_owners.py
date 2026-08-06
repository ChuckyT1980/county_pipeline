"""Rebuild northern_ca export with all owner names:
  - Tehama: propagate assessee_name -> owner_name
  - Shasta: use recorder doc search grantee names"""
import csv, os, json

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Tehama: load ALL enriched rows ---
tehama_rows = []
with open(os.path.join(base_dir, 'tax_pipeline/tehama_MASTER_leads_enriched.csv')) as f:
    for row in csv.DictReader(f):
        tehama_rows.append(row)

# Build lookup map: fee_parcel + apn_pdf -> owner name
tehama_lookup = {}
for row in tehama_rows:
    fee = row.get('fee_parcel', '').strip()
    apn_pdf = row.get('apn_pdf', '').strip().replace('-', '')
    owner = row.get('owner_name', '').strip()
    assessee = row.get('assessee_name', '').strip()
    resolved = owner if (owner and owner != 'SKIP_TRACE_REQUIRED') else assessee
    
    if resolved:
        if fee:
            # Also store without .0 suffix and without leading zeros
            fee_clean = fee.replace('.0', '')
            tehama_lookup[fee] = resolved
            tehama_lookup[fee_clean] = resolved
            norm = fee_clean.lstrip('0')
            if norm != fee_clean:
                tehama_lookup[norm] = resolved
        if apn_pdf:
            tehama_lookup[apn_pdf] = resolved

print(f"Tehama: {len(tehama_rows)} enriched rows, {len(tehama_lookup)} lookup keys")

# --- Shasta: load recorder doc search results ---
shasta_results = json.load(open(os.path.join(base_dir, 'scratch/shasta_doc_search_results.json')))
shasta_grantee_map = {}
for r in shasta_results:
    g = r.get('grantee', '').strip()
    if g:
        shasta_grantee_map[r['apn']] = g

print(f"Shasta: {len(shasta_grantee_map)} APNs with recorder grantee names")

# --- Load and fix export ---
export_path = os.path.join(base_dir, 'northern_ca_MASTER_export.csv')
export_rows = []
with open(export_path) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    import re
    
    for row in reader:
        row = dict(row)
        fee = row.get('fee_parcel', '').strip()
        county = row.get('county', '').strip().lower()
        current_owner = row.get('owner_name', '').strip()
        
        if county == 'tehama':
            if not current_owner or current_owner == 'SKIP_TRACE_REQUIRED':
                # Try fee_parcel lookup
                resolved = False
                lookup_key = fee
                
                # If no fee_parcel, extract from verified_url
                if not lookup_key:
                    vurl = row.get('verified_url', '')
                    m = re.search(r'/tehama/tax/main/(\d+)/', vurl)
                    if m:
                        lookup_key = m.group(1)
                
                if not lookup_key:
                    pass
                elif lookup_key in tehama_lookup:
                    row['owner_name'] = tehama_lookup[lookup_key]
                    row['notes'] = f'Owner from enriched file'
                    print(f"  Tehama {lookup_key:20s} -> {tehama_lookup[lookup_key][:40]}")
                    resolved = True
                else:
                    # Try normalized (strip leading zeros)
                    norm_key = lookup_key.lstrip('0')
                    if norm_key in tehama_lookup:
                        row['owner_name'] = tehama_lookup[norm_key]
                        row['notes'] = f'Owner from enriched file (norm)'
                        print(f"  Tehama norm {lookup_key:20s} -> {tehama_lookup[norm_key][:40]}")
                        resolved = True
                
                if not resolved:
                    print(f"  Tehama COULD NOT FIX fee={fee:20s} url_key={lookup_key:20s}")
        
        elif county == 'shasta':
            if not current_owner or current_owner == 'SKIP_TRACE_REQUIRED':
                apn = row.get('apn', '').strip()
                # Check by fee_parcel (Shasta doc_data keys are fee_parcels)
                grantee = shasta_grantee_map.get(fee, '') or shasta_grantee_map.get(apn, '')
                if grantee:
                    row['owner_name'] = grantee
                    row['recorder_info'] = f'Recorder: most recent deed grantee = {grantee}'
                    print(f"  Shasta fee={fee:20s} -> {grantee[:40]}")
        
        export_rows.append(row)

# Write fixed export
output_path = os.path.join(base_dir, 'northern_ca_MASTER_export_with_owners.csv')
with open(output_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(export_rows)

print(f"\nWritten {len(export_rows)} rows to {output_path}")

# Final summary
print("\n=== Final Owner Name Summary ===")
for row in export_rows:
    county = row.get('county', '?')
    fee = row.get('fee_parcel', '').strip()
    owner = row.get('owner_name', '').strip()
    balance = row.get('total_balance', '?')
    print(f"  {county:8s} fee={fee:20s} owner={owner[:40] if owner else 'EMPTY':40s} bal={balance:>10s}")
