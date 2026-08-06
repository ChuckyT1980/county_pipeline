"""
Analyze 104 Butte County auction parcels for best acquisition targets.
Criteria: score >= 50, positive equity (value > min bid), low bid-to-value ratio, strong liens.
Output: tiered recommendation report + top targets CSV.
"""
import csv, json

BASE = r"C:\Users\chuck\Downloads\county_pipeline\tax_pipeline"

rows = []
with open(BASE + '/butte_auction_all_105_enriched.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        apn = row['apn_dash']
        # Skip unenriched
        if row.get('source') in ('NOT_ENRICHED', 'FRESH') or not row.get('score') or row['score'] == '0':
            continue
        r = {
            'apn': apn,
            'owner': row.get('owner_name', ''),
            'pdf_owner': row['pdf_owner'][:50],
            'min_bid': int(row['min_bid']) if row['min_bid'] and row['min_bid'].isdigit() else 0,
            'score': int(row['score']) if row['score'].isdigit() else 0,
            'assessed': int(row['net_assessed_value']) if row['net_assessed_value'] and row['net_assessed_value'].isdigit() else 0,
            'max_bid': int(row['max_bid_threshold']) if row['max_bid_threshold'] and row['max_bid_threshold'].isdigit() else 0,
            'bid_pct': row['bid_to_value_pct'],
            'mortgages': int(row['total_open_mortgages']) if row['total_open_mortgages'] and row['total_open_mortgages'].isdigit() else 0,
            'liens': row['open_lien_types'],
            'assignment': row['has_assignment_of_rents'] == 'True',
            'nod': row['notice_of_default_present'] == 'True',
            'ttd': row['has_trustee_deed'] == 'True',
            'doc_count': int(row['recorder_doc_count']) if row['recorder_doc_count'] and row['recorder_doc_count'].isdigit() else 0,
            'entity': row['entity_type'],
        }
        
        # Compute equity = conservative value minus min bid
        if r['assessed'] > 0:
            conservative_value = int(r['assessed'] * 0.7)
            r['equity'] = max(0, conservative_value - r['min_bid'])
            r['bid_to_value'] = round(r['min_bid'] / r['assessed'] * 100, 1)
        else:
            r['equity'] = 0
            r['bid_to_value'] = 999
        
        rows.append(r)

# TIER 1: Score >= 80, positive equity
tier1 = [r for r in rows if r['score'] >= 80 and r['equity'] > 0]
tier1.sort(key=lambda r: (-r['score'], -r['equity']))

# TIER 2: Score 50-79, positive equity
tier2 = [r for r in rows if 50 <= r['score'] < 80 and r['equity'] > 0]
tier2.sort(key=lambda r: (-r['score'], -r['equity']))

# TIER 3: Score >= 50, zero equity (vacant land, no improvements, or underwater)
tier3 = [r for r in rows if r['score'] >= 50 and r['equity'] == 0]
tier3.sort(key=lambda r: (-r['score'], r['bid_to_value']))

# TIER 4: Score < 50
tier4 = [r for r in rows if r['score'] < 50]
tier4.sort(key=lambda r: (-r['score'], -r['equity']))

print("=" * 100)
print("BUTTE COUNTY TAX DEFAULT AUCTION — TARGET ANALYSIS (Aug 7-10, 2026)")
print("=" * 100)
print()

print("TIER 1: HIGH-INTEREST (score >= 80, positive equity)")
print("-" * 100)
print("%-30s %-25s %5s %8s %8s %8s %6s %8s %s" % ("APN", "Owner", "Score", "Min Bid", "Assess", "Max Bid", "B/V%", "Equity", "Liens"))
for r in tier1:
    print("%-30s %-25s %5d %8s %8s %8s %5.1f%% %8s %s" % (
        r['apn'], r['owner'][:24], r['score'],
        '$%d' % r['min_bid'], '$%d' % r['assessed'], '$%d' % r['max_bid'],
        r['bid_to_value'], '$%d' % r['equity'],
        r['liens'][:50] if r['liens'] else 'none'
    ))

print()
print("TIER 2: GOOD-INTEREST (score 50-79, positive equity)")
print("-" * 100)
print("%-30s %-25s %5s %8s %8s %8s %6s %8s" % ("APN", "Owner", "Score", "Min Bid", "Assess", "Max Bid", "B/V%", "Equity"))
for r in tier2:
    print("%-30s %-25s %5d %8s %8s %8s %5.1f%% %8s" % (
        r['apn'], r['owner'][:24], r['score'],
        '$%d' % r['min_bid'], '$%d' % r['assessed'], '$%d' % r['max_bid'],
        r['bid_to_value'], '$%d' % r['equity']
    ))

print()
print("TIER 3: ZERO EQUITY (score >= 50, no assessed value or underwater)")
print("-" * 100)
if tier3:
    print("%-30s %-25s %5s %8s %8s" % ("APN", "Owner", "Score", "Min Bid", "Assess"))
    for r in tier3:
        print("%-30s %-25s %5d %8s %8s" % (
            r['apn'], r['owner'][:24], r['score'],
            '$%d' % r['min_bid'], '$%d' % r['assessed'] if r['assessed'] else 'NONE'
        ))
else:
    print("  (none)")

print()
print("TIER 4: LOW SCORE (score < 50)")
print("-" * 100)
for r in tier4:
    eq_str = '$%d' % r['equity'] if r['equity'] else 'none'
    print("  %-25s %-25s score=%d min=%s assess=%s equity=%s b/v=%.1f%%" % (
        r['apn'], r['owner'][:24], r['score'],
        '$%d' % r['min_bid'], '$%d' % r['assessed'] if r['assessed'] else 'NONE',
        eq_str, r['bid_to_value']
    ))

print()
print("=" * 100)
print("SUMMARY")
print("  Tier 1 (80+, equity): %d parcels" % len(tier1))
print("  Tier 2 (50-79, equity): %d parcels" % len(tier2))
print("  Tier 3 (50+, no equity): %d parcels" % len(tier3))
print("  Tier 4 (< 50): %d parcels" % len(tier4))
print("  Total enriched: %d" % len(rows))

# Top 10 composite ranking
print()
print("TOP 10 OVERALL (composite: score * equity_ratio)")
print("-" * 80)
composite = []
for r in rows:
    if r['assessed'] > 0:
        equity_ratio = r['equity'] / r['assessed']
    else:
        equity_ratio = 0
    # composite: score * equity_ratio, weight equity for real $ returns
    composite_val = r['score'] * equity_ratio * r['assessed'] / 1000
    if r['score'] >= 50 and r['equity'] > 0:
        composite.append((r, composite_val))

composite.sort(key=lambda x: -x[1])
for i, (r, cv) in enumerate(composite[:10]):
    print("  %d. %-25s score=%d min=$%-6s equity=$%-6s b/v=%.1f%% | %s" % (
        i+1, r['apn'], r['score'], r['min_bid'], r['equity'], r['bid_to_value'], r['owner'][:30]
    ))

# Write top targets CSV
fieldnames = ['apn', 'owner', 'score', 'min_bid', 'assessed_value', 'max_bid_threshold',
              'bid_to_value_pct', 'equity', 'tier', 'liens', 'entity']
with open(BASE + '/butte_auction_top_targets.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for r in tier1 + tier2:
        w.writerow({
            'apn': r['apn'],
            'owner': r['owner'],
            'score': r['score'],
            'min_bid': r['min_bid'],
            'assessed_value': r['assessed'],
            'max_bid_threshold': r['max_bid'],
            'bid_to_value_pct': r['bid_to_value'],
            'equity': r['equity'],
            'tier': 1 if r in tier1 else 2,
            'liens': r['liens'],
            'entity': r['entity'],
        })

print()
print("Top targets written to: butte_auction_top_targets.csv")
