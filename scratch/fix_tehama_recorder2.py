"""Fix Tehama recorder info using the debugged matching"""
import csv, os, re

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load enriched: build lookup by both fee_parcel and apn_pdf
tehama_lookup = {}  # key -> (rec_doc_number, rec_doc_date, liens)
with open(os.path.join(base_dir, 'tax_pipeline/tehama_MASTER_leads_enriched.csv')) as f:
    for row in csv.DictReader(f):
        fee = row.get('fee_parcel', '').strip()
        apn_pdf = row.get('apn_pdf', '').strip().replace('-', '')
        rec_doc = row.get('rec_doc_number', '').strip()
        rec_date = row.get('rec_doc_date', '').strip()
        
        if fee:
            tehama_lookup[fee] = (rec_doc, rec_date)
        if apn_pdf:
            tehama_lookup[apn_pdf] = (rec_doc, rec_date)
        # Also store with .0 suffix variation (since some fees have it)
        if fee and fee.endswith('.0'):
            tehama_lookup[fee.replace('.0', '')] = (rec_doc, rec_date)

print(f"Tehama lookup keys: {len(tehama_lookup)}")

# Load and fix export
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
                fee = row.get('fee_parcel', '').strip()
                vurl = row.get('verified_url', '')
                m = re.search(r'/tehama/tax/main/(\d+)/', vurl)
                url_key = m.group(1) if m else ''
                
                # Try lookup by fee, then url_key, then apn
                lookup_key = fee or url_key or row.get('apn', '').strip()
                
                rec_doc, rec_date = '', ''
                if lookup_key in tehama_lookup:
                    rec_doc, rec_date = tehama_lookup[lookup_key]
                else:
                    # Try normalized
                    norm = lookup_key.lstrip('0')
                    for k, v in tehama_lookup.items():
                        if k.replace('.0', '').lstrip('0') == norm:
                            rec_doc, rec_date = v
                            break
                
                if rec_doc:
                    row['recorder_info'] = f'doc {rec_doc} dated {rec_date}'
                    print(f"  Tehama {lookup_key:20s} recorder={rec_doc} {rec_date}")
                else:
                    print(f"  Tehama {lookup_key:20s} NO recorder doc")
        
        rows.append(row)

# Write
with open(export_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
print(f"\nUpdated {export_path}")

# Re-run filter
print("\n=== HIGH-PRESSURE FILTER (>= $7,500) ===")
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

print(f"Qualified: {len(filtered)}")
for r in filtered:
    bal = float(r.get('total_balance', 0) or 0)
    print(f"  {r['owner_name'][:38]:38s} ${bal:>8,.2f}  {r['county']:8s}")
print(f"\nTotal: ${total_bal:,.2f}")
