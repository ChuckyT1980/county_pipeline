import csv, pdfplumber, re

# Load authoritative index
idx = {}
with open('..\\archive\\tax_pipeline\\butte_AUTHORITATIVE_master_index.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        idx[row['apn_dash'].strip()] = row

print('Authoritative index: %d parcels' % len(idx))

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

print('Auction parcels: %d' % len(auction_dash))

# Match auction to index
matched = []
for apn in sorted(auction_dash):
    info = idx.get(apn, {})
    asmt = info.get('asmt', '')
    address = info.get('address', '')
    matched.append({'apn': apn, 'asmt': asmt, 'address': address, 'in_index': apn in idx})

print('\nMatched %d / %d auction parcels in authoritative index\n' % (sum(1 for m in matched if m['in_index']), len(matched)))

# Also check which are in the MASTER leads (which have enrichment data)
master = {}
with open('butte_MASTER_leads_with_liens.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        master[row['asmt'].strip()] = row

# Of the auction parcels, which have enrichment data?
with_enrichment = 0
for m in matched:
    if m['asmt'] in master:
        m['in_master'] = True
        m['master_owner'] = master[m['asmt']].get('owner_name', '')
        m['master_score'] = master[m['asmt']].get('verified_score', '')
        m['master_balance'] = master[m['asmt']].get('v_total_balance', '')
        with_enrichment += 1
    else:
        m['in_master'] = False

print('Auction parcels with enrichment data: %d / %d' % (with_enrichment, len(matched)))

# Show ALL auction parcels with their data status
print('\n%-15s | %-14s | %-6s | %-6s | %-5s | %s' % ('Auction APN', 'Asmt (normalized)', 'InIdx', 'InMstr', 'Score', 'Address'))
print('-' * 100)
for m in matched:
    score = master[m['asmt']].get('verified_score', '-') if m['in_master'] else '-'
    addr = (m['address'] or '')[:50]
    print('%-15s | %-14s | %-6s | %-6s | %-5s | %s' % (m['apn'], m['asmt'], 'Y' if m['in_index'] else 'N', 'Y' if m['in_master'] else 'N', score, addr))
