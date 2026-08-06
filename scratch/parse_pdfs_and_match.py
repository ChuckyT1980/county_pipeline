"""Parse all Shasta PDFs, build APN->owner lookup, match against MASTER leads"""
import pdfplumber, re, json, os, pandas as pd
from pathlib import Path

DOWNLOADS = Path.home() / "Downloads"
PROJECT = Path(__file__).parent.parent

PDFS = [
    DOWNLOADS / "june_2025_legal_publication_-_impending_power_to_sell.pdf",
    DOWNLOADS / "first_year_delinquent_list_2025_-_page_1.pdf",
    DOWNLOADS / "fist_year_delinquent_llist_2025_-_page_2.pdf",
    DOWNLOADS / "december_2025_-_notice_of_public_auction.pdf",
    DOWNLOADS / "notice_of_excess_proceeds_for_2025_auction.pdf",
]

APN_RE = re.compile(r'(\d{3}[-.]?\d{3}[-.]?\d{3}[-.]?\d{3})')

def normalize(apn):
    d = re.sub(r'\D', '', apn)
    if len(d) == 12:
        return '%s-%s-%s-%s' % (d[:3], d[3:6], d[6:9], d[9:12])
    return apn

def parse_pdf(path):
    """Extract APN -> owner name mappings from a Shasta tax PDF."""
    records = {}  # norm_apn -> owner_name
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            full_text = ' '.join(lines)
            
            # Pattern: APN followed by owner name, possibly followed by amount
            # Format: "044-150-017-000 TEIXEIRA YVONNE J & BARAHONA EDWIN $5,622.86"
            # Or in the excess proceeds: APN on one line, name on next
            # Better approach: find APNs, then extract owner name between APN and $ amount
            
            for line in lines:
                apn_match = APN_RE.search(line)
                if not apn_match:
                    continue
                
                apn_raw = apn_match.group(1)
                norm_apn = normalize(apn_raw)
                
                # Skip header/instruction lines that aren't real records
                if 'ASSESSOR' in line.upper() and 'PARCEL' in line.upper():
                    continue
                if 'PARCEL NUMBERING' in line.upper():
                    continue
                if 'EXPLANATION' in line.upper():
                    continue
                
                # Extract owner name: text between APN and dollar amount (or end of line)
                rest = line[apn_match.end():].strip()
                
                # Remove leading/trailing noise
                # Some entries have two APNs per line (delinquent lists)
                other_apn = APN_RE.search(rest)
                
                # Check for dollar amount
                amount_match = re.search(r'\$[\d,]+\.?\d*', rest)
                if amount_match:
                    owner = rest[:amount_match.start()].strip()
                elif other_apn:
                    # Two APNs on same line - take text between them
                    owner = rest[:other_apn.start()].strip()
                else:
                    owner = rest.strip()
                
                # Clean up owner name
                owner = re.sub(r'\s+', ' ', owner).strip().rstrip(',')
                
                if owner and len(owner) > 2 and norm_apn not in records:
                    records[norm_apn] = owner
    
    return records

# Parse all PDFs
all_owners = {}
for path in PDFS:
    name = os.path.basename(path)
    records = parse_pdf(path)
    print('%s: %d owner records' % (name, len(records)))
    for apn, owner in records.items():
        if apn not in all_owners:
            all_owners[apn] = owner

print('\nTotal unique APN->owner mappings: %d' % len(all_owners))

# Save lookup
with open(PROJECT / 'scratch' / 'shasta_pdf_owners.json', 'w') as f:
    json.dump(all_owners, f, indent=2)
print('Saved lookup to scratch/shasta_pdf_owners.json')

# Match against MASTER leads
master = pd.read_csv(PROJECT / 'tax_pipeline' / 'shasta_MASTER_leads.csv')
master['fee_parcel_norm'] = master['fee_parcel'].apply(lambda x: normalize(str(x)) if pd.notna(x) else '')

matched = 0
for i, row in master.iterrows():
    apn = row['fee_parcel_norm']
    if apn in all_owners:
        matched += 1

print('\nMASTER leads: %d' % len(master))
print('Matched to PDF owner: %d' % matched)
print('Match rate: %.1f%%' % (matched / len(master) * 100))

# Show which MASTER leads matched and which didn't
master['pdf_owner'] = master['fee_parcel_norm'].map(all_owners)
matched_df = master[master['pdf_owner'].notna()]
unmatched_df = master[master['pdf_owner'].isna()]

print('\n=== Matched (%d) ===' % len(matched_df))
for _, r in matched_df.head(20).iterrows():
    b = r.get('v_total_balance', '')
    print('  %s -> %-50s bal=%s' % (r['fee_parcel_norm'], r['pdf_owner'][:48], str(b)[:12]))

print('\n=== Unmatched (%d) ===' % len(unmatched_df))
for _, r in unmatched_df.head(10).iterrows():
    print('  %s %s' % (r['fee_parcel_norm'], str(r.get('address', ''))[:40]))

# Also check the 12 export leads specifically
export = pd.read_csv(PROJECT / 'northern_ca_MASTER_export.csv')
shasta_export = export[export['county'] == 'shasta']
print('\n=== Shasta Export leads (12) owner match ===')
for _, r in shasta_export.iterrows():
    apn = normalize(str(r['fee_parcel']))
    owner = all_owners.get(apn, 'NO MATCH')
    print('  %s -> %s' % (apn, owner[:50] if len(owner) > 50 else owner))
