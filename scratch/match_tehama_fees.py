"""Match URL fee parcels to enriched file entries"""
import csv, os, re

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load enriched file
enriched = {}
with open(os.path.join(base_dir, 'tax_pipeline/tehama_MASTER_leads_enriched.csv')) as f:
    for row in csv.DictReader(f):
        fee = row.get('fee_parcel', '').strip()
        if fee:
            # Store both raw and cleaned versions
            fee_clean = fee.replace('.0', '').replace('-', '')
            enriched[fee_clean] = row
            enriched[fee] = row

# Load export to get the URL fee parcels
url_fees = set()
with open(os.path.join(base_dir, 'northern_ca_MASTER_export.csv')) as f:
    for row in csv.DictReader(f):
        if row.get('county', '').strip().lower() == 'tehama' and not row.get('fee_parcel', '').strip():
            vurl = row.get('verified_url', '')
            m = re.search(r'/tehama/tax/main/(\d+)/', vurl)
            if m:
                url_fees.add(m.group(1))

print(f"URL fee parcels ({len(url_fees)}):")
for uf in sorted(url_fees):
    print(f"  {uf}")

# Try to match each URL fee to an enriched entry
print("\n\nMatching attempts:")
for uf in sorted(url_fees):
    # Search enriched keys
    match = None
    for ek, er in enriched.items():
        ek_clean = ek.replace('.0', '').replace('-', '')
        # Check if they match with different leading zero patterns
        if ek_clean == uf.lstrip('0') or ek_clean == uf or uf.endswith(ek_clean):
            match = (ek, er)
            break
    
    if match:
        ek, er = match
        print(f"  {uf} -> matched key={ek} assessee={er.get('assessee_name','?'):30s} owner_name={er.get('owner_name','?'):30s}")
    else:
        print(f"  {uf} -> NO MATCH in enriched")
        
        # Debug: show all enriched keys
        print(f"  Enriched keys sample:")
        for ek in sorted(enriched.keys())[:5]:
            print(f"    {ek}")
        break  # Just show first miss
