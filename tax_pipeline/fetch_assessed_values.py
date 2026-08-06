#!/usr/bin/env python3
"""
Fetch Net Assessed Values from AsrPrint for all 104 auction parcels.
Then merge into the targeting CSV with max bid calculations.
"""
import csv, re, requests, concurrent.futures
from bs4 import BeautifulSoup

BASE = r"C:\Users\chuck\Downloads\county_pipeline\tax_pipeline"
TARGET_CSV = BASE + r"\butte_auction_targets_complete.csv"
OUTPUT_CSV = BASE + r"\butte_auction_targets_with_values.csv"
IDX_CSV = BASE + r"\..\archive\tax_pipeline\butte_AUTHORITATIVE_master_index.csv"

# Load authoritative index to get asmt for each apn_dash
idx = {}
with open(IDX_CSV, encoding='utf-8') as f:
    for row in csv.DictReader(f):
        idx[row['apn_dash'].strip()] = row['asmt'].strip()

# Load existing targeting CSV
targets = []
with open(TARGET_CSV, encoding='utf-8') as f:
    for row in csv.DictReader(f):
        targets.append(row)

print("Loaded %d targets" % len(targets))

# Fetch AsrPrint for each parcel
def fetch_value(apn_dash):
    asmt = idx.get(apn_dash, '')
    if not asmt:
        return (apn_dash, None, None, None)
    
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://common1.mptsweb.com/mbap/butte/asr",
    })
    try:
        r = s.get("https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/%s" % asmt, timeout=15)
        if r.status_code != 200:
            return (apn_dash, None, None, r.status_code)
        
        soup = BeautifulSoup(r.text, "html.parser")
        net_value = None
        land_value = None
        impr_value = None
        property_type = None
        acres = None
        situs = None
        
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if "Net Assessed Value" in label:
                    net_value = value.replace('$', '').replace(',', '').strip()
                elif "Land" in label:
                    land_value = value.replace('$', '').replace(',', '').strip()
                elif "Structural Imprv" in label:
                    impr_value = value.replace('$', '').replace(',', '').strip()
                elif "Property Type" in label:
                    property_type = value.strip()
                elif "Lot Size(Acres)" in label:
                    acres = value.strip()
                elif "SitusAddr" in label:
                    situs = value.strip()
        
        return (apn_dash, net_value, land_value, impr_value)
    except Exception as e:
        return (apn_dash, None, None, str(e))

# Batch fetch
padded = [t['apn_dash'] for t in targets]
values = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    fut = {ex.submit(fetch_value, a): a for a in padded}
    for f in concurrent.futures.as_completed(fut):
        apn, net, land, impr = f.result()
        values[apn] = {'net_assessed': net, 'land_value': land, 'impr_value': impr}

resolved = sum(1 for v in values.values() if v['net_assessed'])
print("Assessed values fetched: %d / %d" % (resolved, len(targets)))

# Merge values into targets and calculate max bid
fieldnames = list(targets[0].keys()) if targets else []
extra_cols = ['net_assessed_value', 'land_value', 'impr_value', 'max_bid_threshold', 'bid_to_value_pct']
for c in extra_cols:
    if c not in fieldnames:
        fieldnames.append(c)

for t in targets:
    apn = t['apn_dash']
    v = values.get(apn, {})
    net = v.get('net_assessed')
    t['net_assessed_value'] = net or ''
    t['land_value'] = v.get('land_value', '')
    t['impr_value'] = v.get('impr_value', '')
    
    # Calculate max bid threshold: 70% of assessed value (standard tax sale ceiling)
    try:
        assessed = float(net) if net else 0
        min_bid = int(t.get('min_bid', 0) or 0)
        max_bid = int(assessed * 0.7)
        t['max_bid_threshold'] = str(max_bid)
        if min_bid > 0 and assessed > 0:
            t['bid_to_value_pct'] = "%.1f%%" % (min_bid / assessed * 100)
        else:
            t['bid_to_value_pct'] = ''
    except:
        t['max_bid_threshold'] = ''
        t['bid_to_value_pct'] = ''

# Sort by score descending (maintain existing order)
targets.sort(key=lambda r: int(r.get('score', 0) or 0), reverse=True)

with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(targets)

print("Wrote %s" % OUTPUT_CSV)

# Summary
print("\n=== TOP 20 WITH VALUES ===")
h = "%-18s | %-25s | Score | Min Bid    | Assessed     | Max Bid(70%%) | B/V %%"
print(h)
print("-" * len(h))
for t in targets[:20]:
    name = (t.get('owner_name','') or 'UNKNOWN')[:25]
    bid = "$%s" % t['min_bid'] if t.get('min_bid') else "?"
    assessed = "$%s" % t['net_assessed_value'] if t.get('net_assessed_value') else "?"
    max_bid = "$%s" % t['max_bid_threshold'] if t.get('max_bid_threshold') else "?"
    bv = t.get('bid_to_value_pct', '')
    print("%-18s | %-25s | %5s | %-10s | %-13s | %-12s | %s" % (
        t['apn_dash'], name, t.get('score',''), bid, assessed, max_bid, bv))

# Stats
with_values = [t for t in targets if t.get('net_assessed_value')]
if with_values:
    vals = [int(t['net_assessed_value']) for t in with_values if t['net_assessed_value'].isdigit()]
    if vals:
        print("\nAssessed value stats (from %d parcels with data):" % len(vals))
        print("  Total: $%s" % "{:,}".format(sum(vals)))
        print("  Average: $%s" % "{:,}".format(int(sum(vals)/len(vals))))
        print("  Median: $%s" % "{:,}".format(sorted(vals)[len(vals)//2]))
        print("  Min: $%s" % "{:,}".format(min(vals)))
        print("  Max: $%s" % "{:,}".format(max(vals)))
