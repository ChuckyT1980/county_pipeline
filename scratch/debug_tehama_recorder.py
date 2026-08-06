"""Debug Tehama recorder matching"""
import csv, os, re

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load enriched file keys
enriched_keys = set()
with open(os.path.join(base_dir, 'tax_pipeline/tehama_MASTER_leads_enriched.csv')) as f:
    for row in csv.DictReader(f):
        fee = row.get('fee_parcel', '').strip()
        apn_pdf = row.get('apn_pdf', '').strip().replace('-', '')
        if fee: enriched_keys.add(f'fee={fee}')
        if apn_pdf: enriched_keys.add(f'apn={apn_pdf}')

print("Enriched keys sample (first 20):")
for k in sorted(enriched_keys)[:20]:
    print(f"  {k}")

# Load export Tehama rows
print("\n\nExport Tehama rows:")
with open(os.path.join(base_dir, 'northern_ca_MASTER_export_with_owners.csv')) as f:
    for row in csv.DictReader(f):
        if row.get('county', '').strip().lower() == 'tehama':
            fee = row.get('fee_parcel', '').strip()
            vurl = row.get('verified_url', '')
            apn = row.get('apn', '').strip()
            m = re.search(r'/tehama/tax/main/(\d+)/', vurl)
            url_key = m.group(1) if m else 'N/A'
            owner = row.get('owner_name', '').strip()
            print(f"  fee='{fee}' url_key={url_key} apn='{apn}' owner='{owner[:30]}'")
            
            # Try matching
            lookup = fee if fee else url_key
            print(f"    lookup={lookup}")
            
            # Check if exists in enriched
            found = False
            for ek in enriched_keys:
                if lookup in ek or ek.replace('.0','').lstrip('0') == lookup.lstrip('0'):
                    print(f"    MATCHED: {ek}")
                    found = True
                    break
            if not found:
                # Check apn_pdf matching
                lookup_clean = lookup.lstrip('0')
                for ek in enriched_keys:
                    ek_clean = ek.replace('fee=','').replace('apn=','').replace('.0','').lstrip('0')
                    if ek_clean == lookup_clean:
                        print(f"    NORM MATCHED: {ek}")
                        found = True
                        break
            if not found:
                print(f"    NO MATCH")
