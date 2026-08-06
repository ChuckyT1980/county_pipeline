"""Search enriched file for rows matching URL fee parcels"""
import csv, os, re

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

url_fees = [
    '103040024000', '073260053000', '013220002000', '011390013000',
    '078400037000', '075250043000', '021230006000', '079330003000', '078270009000'
]

# Load enriched file
enriched = []
with open(os.path.join(base_dir, 'tax_pipeline/tehama_MASTER_leads_enriched.csv')) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    print(f"Enriched columns: {fieldnames}")
    print()
    for row in reader:
        enriched.append(row)

print(f"Total enriched rows: {len(enriched)}")

# For each URL fee, search every field in every row
for uf in url_fees:
    print(f"\n--- Searching for {uf} ---")
    matches = []
    for row in enriched:
        for k, v in row.items():
            if v and uf in v.replace('-', '').replace('.0', ''):
                matches.append((row, k))
                break
    
    if matches:
        for row, match_field in matches:
            fee = row.get('fee_parcel', '').strip()
            apn = row.get('apn_pdf', '').strip()
            assessee = row.get('assessee_name', '').strip()
            owner = row.get('owner_name', '').strip()
            asr_url = row.get('asrprint_url', '').strip()
            source = row.get('source', '').strip()
            situs = row.get('situs_pdf', '').strip()
            print(f"  MATCH on {match_field}: fee={fee:20s} apn={apn:20s} assessee={assessee[:40]:40s} owner={owner[:20]:20s} source={source}")
    else:
        print(f"  NO MATCH found in any field")
        
        # Also check if it's in the MASTER leads file
        with open(os.path.join(base_dir, 'tax_pipeline/tehama_MASTER_leads.csv')) as f:
            for row in csv.DictReader(f):
                for k, v in row.items():
                    if v and uf in v.replace('-', '').replace('.0', ''):
                        print(f"  FOUND in MASTER leads: {k}={v}")
                        break
