"""Debug why Tehama URL fee parcels don't match enriched file"""
import csv, os, re

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load enriched file - show ALL fee parcels
enriched_fees = set()
enriched_data = {}
with open(os.path.join(base_dir, 'tax_pipeline/tehama_MASTER_leads_enriched.csv')) as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        fee = row.get('fee_parcel', '').strip()
        if fee:
            fee_clean = fee.replace('.0', '')
            # Also try adding/removing leading zeros to get 12 digits
            enriched_fees.add(fee_clean)
            enriched_data[fee_clean] = row
            
            # Try left-padded to 12 digits
            if len(fee_clean) < 12:
                padded = fee_clean.zfill(12)
                enriched_fees.add(padded)
                enriched_data[padded] = row

print(f"Enriched fee parcels ({len(enriched_fees)}):")
for ef in sorted(enriched_fees)[:30]:
    print(f"  {ef}")

# URL parcels
url_fees = [
    '103040024000', '073260053000', '013220002000', '011390013000',
    '078400037000', '075250043000', '021230006000', '079330003000', '078270009000'
]

print(f"\n\nLooking for URL parcels in enriched:")
for uf in url_fees:
    # Try exact match
    if uf in enriched_fees:
        print(f"  {uf} -> EXACT MATCH: assessee={enriched_data[uf].get('assessee_name','?'):30s}")
    else:
        # Try lstrip 0
        uf_norm = uf.lstrip('0')
        found = False
        for ef in enriched_fees:
            ef_norm = ef.lstrip('0')
            if ef_norm == uf_norm:
                print(f"  {uf} -> NORM MATCH: {ef} assessee={enriched_data[ef].get('assessee_name','?'):30s}")
                found = True
                break
        if not found:
            print(f"  {uf} -> NO MATCH")
            # Show closest matches
            print(f"     Enriched fees ending with same last 6 digits:")
            for ef in sorted(enriched_fees):
                if ef[-6:] == uf[-6:]:
                    print(f"       {ef} -> {enriched_data[ef].get('assessee_name','?')[:40]}")
