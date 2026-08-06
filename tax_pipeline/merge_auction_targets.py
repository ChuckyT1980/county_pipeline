#!/usr/bin/env python3
"""
Merge 14 already-enriched auction parcels with 89 newly enriched ones.
Output: butte_auction_targets_complete.csv — sorted by score descending.
"""
import csv

ENRICHED_CSV = "butte_auction_enriched.csv"
SCORED_CSV = "butte_scored_leads_rerun.csv"
OUTPUT_CSV = "butte_auction_targets_complete.csv"

# Load min bids from PDF
min_bids = {}
import pdfplumber, re
with pdfplumber.open('reoffer_aug2026.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            for line in text.split('\n'):
                m = re.match(r'(\d{3}-\d{3}-\d{3}-\d{3})\s+(.+)\s+\$?\s*([\d,]+)\s*$', line.strip())
                if m:
                    min_bids[m.group(1)] = int(m.group(3).replace(',',''))

# Load newly enriched (89 parcels)
new_rows = {}
with open(ENRICHED_CSV, encoding='utf-8') as f:
    for row in csv.DictReader(f):
        new_rows[row['apn_dash']] = row

# Load scored rerun (14 auction parcels that are in there)
scored_rows = {}
with open(SCORED_CSV, encoding='utf-8') as f:
    for row in csv.DictReader(f):
        scored_rows[row['parcel_apn']] = row

# Map auction APN dash -> scored rerun data
# The scored rerun uses zero-stripped APNs (1081006000)
# We need the authoritative index to map
IDX_CSV = "..\\archive\\tax_pipeline\\butte_AUTHORITATIVE_master_index.csv"
idx_dash_to_stripped = {}
idx_stripped_to_dash = {}
with open(IDX_CSV, encoding='utf-8') as f:
    for row in csv.DictReader(f):
        apn_dash = row['apn_dash'].strip()
        asmt = row['asmt'].strip()
        stripped = asmt.lstrip('0')
        idx_dash_to_stripped[apn_dash] = stripped
        idx_stripped_to_dash[stripped] = apn_dash

# Build complete list
fieldnames = ['apn_dash', 'address', 'owner_name', 'min_bid', 'score', 'score_reasons',
              'total_open_mortgages', 'open_lien_types', 'has_assignment_of_rents',
              'notice_of_default_present', 'has_trustee_deed', 'recorder_doc_count',
              'entity_type', 'recorder_chain', 'source']

all_auction_apns = sorted(list(min_bids.keys()))
output = []

for apn_dash in all_auction_apns:
    stripped = idx_dash_to_stripped.get(apn_dash, '')
    bid = min_bids.get(apn_dash, 0)

    # Check if in newly enriched
    if apn_dash in new_rows:
        r = new_rows[apn_dash]
        output.append({
            'apn_dash': apn_dash,
            'address': r.get('address', ''),
            'owner_name': r.get('owner_name', ''),
            'min_bid': bid,
            'score': int(r.get('score', 0) or 0),
            'score_reasons': r.get('score_reasons', ''),
            'total_open_mortgages': r.get('total_open_mortgages', '0'),
            'open_lien_types': r.get('open_lien_types', ''),
            'has_assignment_of_rents': r.get('has_assignment_of_rents', 'False'),
            'notice_of_default_present': r.get('notice_of_default_present', 'False'),
            'has_trustee_deed': r.get('has_trustee_deed', 'False'),
            'recorder_doc_count': r.get('recorder_doc_count', '0'),
            'entity_type': r.get('entity_type', ''),
            'recorder_chain': r.get('recorder_chain', ''),
            'source': 'NEWLY_ENRICHED',
        })

    # Check if in scored rerun (14 already-enriched parcels)
    elif stripped in scored_rows:
        r = scored_rows[stripped]
        updated_score = r.get('updated_distress_equity_contact_score', '')
        score = int(updated_score) if updated_score else int(r.get('original_score', 0) or 0)
        # Map mortgage count
        mtg_str = r.get('total_open_mortgages', '0')
        try:
            mtg_count = int(mtg_str)
        except:
            mtg_count = 0

        output.append({
            'apn_dash': apn_dash,
            'address': r.get('situs_address', ''),
            'owner_name': r.get('owner_name', ''),
            'min_bid': bid,
            'score': score,
            'score_reasons': r.get('original_reasons', ''),
            'total_open_mortgages': str(mtg_count),
            'open_lien_types': r.get('open_lien_types', ''),
            'has_assignment_of_rents': '',
            'notice_of_default_present': r.get('notice_of_default_present', 'False'),
            'has_trustee_deed': '',
            'recorder_doc_count': '',
            'entity_type': r.get('entity_type', ''),
            'recorder_chain': r.get('recorder_chain', '')[:200],
            'source': 'ALREADY_ENRICHED',
        })

    else:
        # Not enriched at all (2 missing from index)
        output.append({
            'apn_dash': apn_dash,
            'address': '',
            'owner_name': '',
            'min_bid': bid,
            'score': 0,
            'score_reasons': 'No enrichment data',
            'total_open_mortgages': '0',
            'open_lien_types': '',
            'has_assignment_of_rents': 'False',
            'notice_of_default_present': 'False',
            'has_trustee_deed': 'False',
            'recorder_doc_count': '0',
            'entity_type': '',
            'recorder_chain': '',
            'source': 'NOT_ENRICHED',
        })

# Sort by score descending
output.sort(key=lambda r: r['score'], reverse=True)

# Write
with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(output)

print("=== COMPLETE AUCTION TARGETING LIST ===")
print("Written to: %s" % OUTPUT_CSV)
print("Total: %d auction parcels" % len(output))
print("  Score >= 80: %d" % len([r for r in output if r['score'] >= 80]))
print("  Score 50-79: %d" % len([r for r in output if 50 <= r['score'] < 80]))
print("  Score 25-49: %d" % len([r for r in output if 25 <= r['score'] < 50]))
print("  Score 0-24:  %d" % len([r for r in output if r['score'] < 25]))
print("\nSource breakdown:")
print("  Newly enriched: %d" % len([r for r in output if r['source'] == 'NEWLY_ENRICHED']))
print("  Already enriched: %d" % len([r for r in output if r['source'] == 'ALREADY_ENRICHED']))
print("  Not enriched: %d" % len([r for r in output if r['source'] == 'NOT_ENRICHED']))

print("\n=== TOP 20 TARGETS ===")
h = "%-18s | %-30s | Score | Min Bid   | Mtg | Source"
print(h)
print("-" * len(h))
for r in output[:20]:
    bid_str = "$%s" % r['min_bid'] if r['min_bid'] else "?"
    print("%-18s | %-30s | %5d | %-9s | %3s | %s" % (
        r['apn_dash'], (r['owner_name'] or 'UNKNOWN')[:30],
        r['score'], bid_str, r['total_open_mortgages'],
        'NEW' if r['source'] == 'NEWLY_ENRICHED' else 'OLD'))
