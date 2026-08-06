import csv, pdfplumber, re

# Parse auction APNs
auction_dash = set()
with pdfplumber.open('reoffer_aug2026.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            for line in text.split('\n'):
                m = re.match(r'(\d{3}-\d{3}-\d{3}-\d{3})', line.strip())
                if m:
                    auction_dash.add(m.group(1))

# Load MASTER (has enrichment: owner_name, recorder data, etc.)
master = {}
with open('butte_MASTER_leads_with_liens.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        master[row['asmt'].strip()] = row

# Load scored rerun (has verification status, scores, recorder chain)
scored = {}
with open('butte_scored_leads_rerun.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        scored[row['parcel_apn'].strip()] = row

# Load authoritative index (to get asmt -> apn_dash mapping)
idx = {}
with open('..\\archive\\tax_pipeline\\butte_AUTHORITATIVE_master_index.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        idx[row['apn_dash'].strip()] = row

# For each auction parcel, figure out enrichment status
# Auction: 001-081-006-000 -> lstrip('0') of non-dash = 1081006000
# MASTER asmt: 1081006000 (no leading zeros)
# Scored parcel_apn: 1081006000

already_enriched = 0
needs_enrich = 0
missing_from_idx = 0
enriched_parcels = []
unenriched_parcels = []

for apn_dash in sorted(auction_dash):
    info = idx.get(apn_dash, {})
    asmt = info.get('asmt', '').strip()
    
    # Normalize: strip leading zeros
    asmt_stripped = asmt.lstrip('0') if asmt else ''
    
    # Check if in MASTER or scored
    in_master = asmt_stripped in master
    in_scored = asmt_stripped in scored
    
    if in_scored:
        already_enriched += 1
        enriched_parcels.append({
            'apn_dash': apn_dash,
            'asmt': asmt_stripped,
            'owner': scored[asmt_stripped].get('owner_name', ''),
            'score': scored[asmt_stripped].get('updated_distress_equity_contact_score', ''),
            'verification': scored[asmt_stripped].get('verification_status', ''),
            'mortgages': scored[asmt_stripped].get('total_open_mortgages', ''),
            'liens': scored[asmt_stripped].get('open_lien_types', '')[:60],
        })
    elif not asmt:
        missing_from_idx += 1
    else:
        needs_enrich += 1
        unenriched_parcels.append({
            'apn_dash': apn_dash,
            'asmt': asmt,
            'address': info.get('address', ''),
        })

print("=== REAL ENRICHMENT STATUS OF AUCTION PARCELS ===")
print()
print("Total auction parcels: %d" % len(auction_dash))
print("  Already enriched (in scored leads): %d  (%.1f%%)" % (already_enriched, 100*already_enriched/len(auction_dash)))
print("  Needs enrichment: %d  (%.1f%%)" % (needs_enrich, 100*needs_enrich/len(auction_dash)))
print("  Missing from authoritative index: %d" % missing_from_idx)

print("\n=== ALREADY ENRICHED (%d parcels) ===" % len(enriched_parcels))
print("%-18s | %-30s | Score | Verify         | Mtg | Liens" % ("Auction APN", "Owner"))
print("-" * 90)
for p in enriched_parcels:
    print("%-18s | %-30s | %5s | %-14s | %3s | %s" % (
        p['apn_dash'], p['owner'][:30], p['score'],
        p['verification'], p['mortgages'], p['liens']))

print("\n=== NEEDS ENRICHMENT (%d parcels) ===" % len(unenriched_parcels))
for p in unenriched_parcels:
    print("  %s | %s" % (p['apn_dash'], p.get('address', '')[:60]))
