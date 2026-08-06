import csv, pdfplumber, re

auction_stripped = set()
with pdfplumber.open('reoffer_aug2026.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            for line in text.split('\n'):
                m = re.match(r'(\d{3}-\d{3}-\d{3}-\d{3})', line.strip())
                if m:
                    apn = m.group(1)
                    auction_stripped.add(apn.replace('-','').lstrip('0'))

print('Auction APNs (normalized):', len(auction_stripped))

master_apns = set()
with open('butte_MASTER_leads_with_liens.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        master_apns.add(row['asmt'].strip())

scored_apns = set()
with open('butte_scored_leads_rerun.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        scored_apns.add(row['parcel_apn'].strip())

in_master = auction_stripped & master_apns
in_scored = auction_stripped & scored_apns
not_in_master = auction_stripped - master_apns

print('In MASTER file:', len(in_master), '/', len(auction_stripped), '(%d%%)' % (100*len(in_master)/len(auction_stripped)))
print('In scored leads:', len(in_scored), '/', len(auction_stripped))
print('In MASTER but not scored:', len(in_master - scored_apns))
print('Not in MASTER at all:', len(not_in_master))

if in_master - scored_apns:
    print('\n--- In MASTER but NOT scored (up to 5) ---')
    count = 0
    with open('butte_MASTER_leads_with_liens.csv', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            apn = row['asmt'].strip()
            if apn in in_master and apn not in scored_apns:
                owner = (row.get('owner_name') or '?')[:30]
                score = row.get('verified_score') or '?'
                bal = row.get('v_total_balance') or '?'
                print('  %s | owner=%s | score=%s | bal=%s' % (apn, owner, score, bal))
                count += 1
                if count >= 5:
                    break

print('\nMASTER file size:', len(master_apns), 'parcels')
print('Scored leads:', len(scored_apns), 'parcels')
