"""Add recorder info for Tehama rows and re-run the filter"""
import csv, os, re

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load enriched file
tehama_enriched = {}
with open(os.path.join(base_dir, 'tax_pipeline/tehama_MASTER_leads_enriched.csv')) as f:
    for row in csv.DictReader(f):
        fee = row.get('fee_parcel', '').strip()
        apn_pdf = row.get('apn_pdf', '').strip().replace('-', '')
        # Store by both keys
        if fee:
            tehama_enriched[fee] = row
        if apn_pdf:
            tehama_enriched[apn_pdf] = row
        # Also store the whole row list for URL matching
        if fee:
            tehama_enriched[fee + '_raw'] = row

# Load export, fix Tehama rows
export_path = os.path.join(base_dir, 'northern_ca_MASTER_export_with_owners.csv')
rows = []
with open(export_path) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        row = dict(row)
        if row.get('county', '').strip().lower() == 'tehama':
            current_rec = row.get('recorder_info', '').strip()
            if not current_rec:
                # Find matching enriched row
                fee = row.get('fee_parcel', '').strip()
                lookup_key = fee
                if not lookup_key:
                    vurl = row.get('verified_url', '')
                    m = re.search(r'/tehama/tax/main/(\d+)/', vurl)
                    if m:
                        lookup_key = m.group(1)
                
                # Try to match
                matched_row = None
                if lookup_key:
                    # Direct match
                    if lookup_key in tehama_enriched:
                        matched_row = tehama_enriched[lookup_key]
                    else:
                        # Try normalized
                        norm = lookup_key.lstrip('0')
                        for ek, ev in tehama_enriched.items():
                            if ek.replace('.0', '').lstrip('0') == norm:
                                matched_row = ev
                                break
                        if not matched_row:
                            # Try by apn_pdf
                            for ek, ev in tehama_enriched.items():
                                e_apn = ev.get('apn_pdf', '').strip().replace('-', '')
                                if e_apn == lookup_key:
                                    matched_row = ev
                                    break
                
                if matched_row:
                    rec_doc = matched_row.get('rec_doc_number', '').strip()
                    rec_date = matched_row.get('rec_doc_date', '').strip()
                    liens = matched_row.get('liens', row.get('liens', '0'))
                    if rec_doc:
                        row['recorder_info'] = f'doc {rec_doc} dated {rec_date}'
                        row['liens'] = liens
                        print(f"  Tehama fee={lookup_key:20s} recorder={rec_doc} liens={liens}")
                    else:
                        print(f"  Tehama fee={lookup_key:20s} NO recorder doc in enriched")
                else:
                    print(f"  Tehama fee={lookup_key:20s} NOT FOUND in enriched")
        
        rows.append(row)

# Write updated
with open(export_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
print(f"\nUpdated {export_path}")

# Re-run the filter
print("\n\n=== HIGH-PRESSURE FILTER ===")
filtered = []
total_bal = 0
for r in rows:
    try:
        balance = float(r.get('total_balance', 0) or 0)
    except:
        balance = 0
    delinquent = r.get('delinquent', '').strip().lower() == 'true'
    status = r.get('inst1_status', '').strip()
    owner = r.get('owner_name', '').strip()
    recorder = r.get('recorder_info', '').strip()
    
    if (delinquent and balance >= 7500 and status in ('LATE', 'DUE')
        and owner and recorder and owner != 'SKIP_TRACE_REQUIRED'):
        filtered.append(r)
        total_bal += balance

print(f"Leads (>= $7,500, delinquent, owner+recorder known): {len(filtered)}")
for r in filtered:
    bal = float(r.get('total_balance', 0) or 0)
    print(f"  {r['owner_name'][:38]:38s} ${bal:>8,.2f}  {r['county']:8s} liens={r.get('liens','?'):5s}")
print(f"\nTotal balance: ${total_bal:,.2f}")
