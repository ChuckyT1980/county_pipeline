import csv, pdfplumber, re

# Parse auction APNs
auction_apns = set()
with pdfplumber.open('reoffer_aug2026.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            for line in text.split('\n'):
                m = re.match(r'(\d{3}-\d{3}-\d{3}-\d{3})', line.strip())
                if m:
                    auction_apns.add(m.group(1))

print(f'Auction parcels: {len(auction_apns)}')

# Build auction lookup: full info
auction_info = {}
with pdfplumber.open('reoffer_aug2026.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            lines = text.split('\n')
            for line in lines:
                m = re.match(r'(\d{3}-\d{3}-\d{3}-\d{3})\s+(.+)\s+\$?\s*([\d,]+)\s*$', line.strip())
                if m:
                    apn = m.group(1)
                    rest = m.group(2).strip()
                    bid = m.group(3)
                    auction_info[apn] = {'apn': apn, 'owner_and_address': rest, 'min_bid': int(bid.replace(',',''))}

print(f'Auction entries with parsed bid: {len(auction_info)}')

# Build lookup: stripped auction APN -> auction APN
auction_stripped = {a.replace('-','').lstrip('0'): a for a in auction_apns}

# Read scored leads
leads = list(csv.DictReader(open('butte_scored_leads_rerun.csv', encoding='utf-8')))

# Match
matches = []
unmatched_auction = set(auction_stripped.keys())
for l in leads:
    apn = l['parcel_apn'].strip()
    if apn in auction_stripped:
        auction_apn = auction_stripped[apn]
        info = auction_info.get(auction_apn, {})
        matches.append({
            'lead_apn': apn,
            'auction_apn': auction_apn,
            'owner': l['owner_name'],
            'score': int(l.get('original_score', 0)),
            'min_bid': info.get('min_bid', 0),
            'address': info.get('owner_and_address', ''),
            'verification': l.get('verification_status', ''),
            'lien_types': l.get('open_lien_types', ''),
            'mortgages': l.get('total_open_mortgages', '0'),
            'reasons': l.get('original_reasons', '')
        })
        unmatched_auction.discard(apn)

matches.sort(key=lambda x: x['score'], reverse=True)

print(f'\n=== CROSS-REFERENCE: {len(matches)} MATCHES ===')
print(f'Auction parcels NOT in our leads: {len(unmatched_auction)}')
print()

header = f"{'Lead APN':>12s} | {'Auction APN':>15s} | {'Owner':25s} | {'Score':>5s} | {'Min Bid':>9s} | {'Mortg':>4s} | {'Verification':15s}"
print(header)
print('-' * len(header))
for m in matches:
    print(f"{m['lead_apn']:>12s} | {m['auction_apn']:>15s} | {m['owner'][:25]:25s} | {m['score']:>5d} | {'$'+str(m['min_bid']):>9s} | {m['mortgages']:>4s} | {m['verification']:15s}")

print(f'\n{"="*60}')
print(f'TOP 10 HIGHEST SCORED AUCTION LEADS')
print(f'{"="*60}')
for m in matches[:10]:
    print(f"\n{m['owner']} (Score: {m['score']}, Min Bid: ${m['min_bid']:,})")
    print(f"  Lead APN: {m['lead_apn']}  Auction: {m['auction_apn']}")
    print(f"  Address: {m['address']}")
    print(f"  Liens: {m['lien_types'][:80]}")
    print(f"  Reasons: {m['reasons'][:80]}")
    print(f"  Open Mortgages: {m['mortgages']}")
    print(f"  Status: {m['verification']}")

# Print unmatched auction parcels
print(f'\n{"="*60}')
print(f'AUCTION PARCELS NOT IN OUR LEADS ({len(unmatched_auction)})')
print(f'{"="*60}')
unmatched_formatted = sorted([auction_stripped[u] for u in unmatched_auction])
for apn in unmatched_formatted:
    info = auction_info.get(apn, {})
    bid = info.get('min_bid', '?')
    owner = info.get('owner_and_address', '?')[:40]
    bid_str = f'${bid:,}' if isinstance(bid, int) else str(bid)
    print(f'  {apn} | {bid_str:>8s} | {owner}')

# Write CSV output
with open('butte_auction_targets.csv', 'w', newline='', encoding='utf-8') as f:
    fieldnames = ['score', 'lead_apn', 'auction_apn', 'owner', 'min_bid', 'address',
                  'verification', 'mortgages', 'lien_types', 'reasons']
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for m in matches:
        w.writerow(m)

print(f'\nWrote butte_auction_targets.csv ({len(matches)} rows)')
