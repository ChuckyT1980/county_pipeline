"""
Step 1: Check if the 2 missing-from-index APNs resolve via AsrPrint.
Step 2: Enrich the combined APN.
Step 3: Fix name extraction bugs (View, Export as CSV).
Step 4: Merge everything into butte_auction_all_105_enriched.csv.
"""
import csv, re, requests, concurrent.futures, pdfplumber
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time

BASE = r"C:\Users\chuck\Downloads\county_pipeline\tax_pipeline"

# === STEP 0: Extract all 105 from PDF properly ===

def extract_all_105():
    parcels = []
    current_apn = None
    current_owner = ""
    
    with pdfplumber.open(BASE + '/reoffer_aug2026.pdf') as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                m_apn = re.match(r'(\d{3}-\d{3}-\d{3}-\d{3})(?:\s*/\s*(\d{3}-\d{3}-\d{3}))?', line)
                if m_apn:
                    if current_apn:
                        parcels.append({'apn': current_apn, 'owner': current_owner.strip().rstrip('$').strip()})
                    current_apn = m_apn.group(1)
                    combined = m_apn.group(2)
                    if combined:
                        current_apn = current_apn + '/' + combined
                    rest = line[m_apn.end():].strip()
                    bid_m = re.search(r'\$[\d,]+', rest)
                    current_owner = rest[:bid_m.start()].strip().rstrip('$').strip() if bid_m else rest
                else:
                    bid_m = re.search(r'\$[\d,]+', line)
                    if bid_m:
                        before_bid = line[:bid_m.start()].strip().rstrip('$').strip()
                        current_owner = (current_owner + ' ' + before_bid).strip()
                    else:
                        current_owner = (current_owner + ' ' + line).strip()
        if current_apn:
            parcels.append({'apn': current_apn, 'owner': current_owner.strip().rstrip('$').strip()})
    return parcels

all_105 = extract_all_105()
print("Total: %d parcels" % len(all_105))

# === STEP 1: Check the 2 missing-from-index APNs and combined APN ===

# These are the ones we need to enrich fresh
need_enrich = [p for p in all_105 if p['apn'] in ('033-067-003-000', '066-420-011-000', '071-270-029-000/990-322-648-000')]
print("\nParcels needing fresh enrichment:")
for p in need_enrich:
    print("  %s | %s" % (p['apn'], p['owner'][:60]))

# Also check if 033-067-003-000 and 066-420-011-000 exist in AsrPrint
# Their APNs without dashes would be: 033067003000 and 066420011000
test_apns = ['033067003000', '066420011000']

def fetch_asr(apn):
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                      "Referer": "https://common1.mptsweb.com/mbap/butte/asr"})
    try:
        r = s.get("https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/" + apn, timeout=15)
        if r.status_code != 200:
            return (apn, None, r.status_code)
        soup = BeautifulSoup(r.text, "html.parser")
        doc_num = None
        assessed = None
        for row in soup.find_all("tr"):
            cells = row.find_all(["td","th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if "Current Document Number" in label and value:
                    doc_num = value.strip()
                if "Net Assessed Value" in label and value:
                    assessed = value.replace('$','').replace(',','').strip()
        return (apn, {'doc_number': doc_num, 'assessed_value': assessed}, 200)
    except Exception as e:
        return (apn, None, str(e))

results = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
    fut = {ex.submit(fetch_asr, a): a for a in test_apns}
    for f in concurrent.futures.as_completed(fut):
        apn, data, status = f.result()
        results[apn] = data
        print("  AsrPrint %s -> doc=%s val=%s (status=%s)" % (apn, data.get('doc_number','NONE') if data else 'FAIL', data.get('assessed_value','NONE') if data else 'FAIL', status))

# === STEP 2: Write the full merged CSV ===

# Load existing enriched data
existing = {}
with open(BASE + '/butte_auction_targets_with_values.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        existing[row['apn_dash']] = row

print("\nExisting enriched: %d" % len(existing))

# Also load the previously enriched 89 for more detail
newly = {}
with open(BASE + '/butte_auction_enriched.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        newly[row['apn_dash']] = row

# Build complete output
fieldnames = ['apn_dash', 'pdf_owner', 'owner_name', 'min_bid', 'score', 'net_assessed_value',
              'total_open_mortgages', 'open_lien_types', 'has_assignment_of_rents',
              'notice_of_default_present', 'has_trustee_deed', 'recorder_doc_count',
              'entity_type', 'max_bid_threshold', 'bid_to_value_pct', 'source']

output = []
for p in all_105:
    apn = p['apn']
    row = {'apn_dash': apn, 'pdf_owner': p['owner'][:80], 'source': 'NOT_ENRICHED'}

    if apn in existing:
        e = existing[apn]
        row.update({
            'owner_name': e.get('owner_name', ''),
            'min_bid': e.get('min_bid', ''),
            'score': e.get('score', ''),
            'net_assessed_value': e.get('net_assessed_value', ''),
            'total_open_mortgages': e.get('total_open_mortgages', '0'),
            'open_lien_types': e.get('open_lien_types', ''),
            'has_assignment_of_rents': e.get('has_assignment_of_rents', 'False'),
            'notice_of_default_present': e.get('notice_of_default_present', 'False'),
            'has_trustee_deed': e.get('has_trustee_deed', 'False'),
            'recorder_doc_count': e.get('recorder_doc_count', '0'),
            'entity_type': e.get('entity_type', ''),
            'max_bid_threshold': e.get('max_bid_threshold', ''),
            'bid_to_value_pct': e.get('bid_to_value_pct', ''),
            'source': e.get('source', 'ENRICHED'),
        })
        # Fix name artifacts from buggy extraction
        if row['owner_name'] in ('View', 'Export as CSV'):
            # Try to get better name from pdf_owner
            pdf_name = p['owner'].split('  ')[0].strip()
            row['owner_name'] = pdf_name if pdf_name else row['owner_name']
    else:
        # Not in existing - these are the 3 missing ones
        row.update({'min_bid': '', 'score': '0', 'source': 'FRESH'})
        # Check if AsrPrint resolved them
        # For the combined APN, we need the primary APN part
        primary_apn = apn.split('/')[0]
        asmt_12 = primary_apn.replace('-', '')
        if asmt_12 in results and results[asmt_12]:
            d = results[asmt_12]
            row['net_assessed_value'] = d.get('assessed_value', '')
            row['owner_name'] = p['owner'].split('  ')[0].strip() if '  ' in p['owner'] else p['owner'][:60]
            if d.get('doc_number'):
                row['owner_name'] = row['owner_name'] + ' (doc: ' + d['doc_number'] + ')'

    output.append(row)

# Sort by score desc, then by APN
output.sort(key=lambda r: (0 - int(r['score']) if r['score'] and r['score'].isdigit() else -9999, r['apn_dash']))

with open(BASE + '/butte_auction_all_105_enriched.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(output)

print("\n=== COMPLETE 105 WRITTEN ===")
print("File: butte_auction_all_105_enriched.csv")

# Summary
scores = [int(r['score']) for r in output if r['score'] and r['score'].isdigit() and int(r['score']) > 0]
print("Parcels with scores > 0: %d" % len(scores))
print("  Score >= 80: %d" % len([s for s in scores if s >= 80]))
print("  Score 50-79: %d" % len([s for s in scores if 50 <= s < 80]))
print("  Score 25-49: %d" % len([s for s in scores if 25 <= s < 50]))

# Flag the 3 formerly missing
print("\n=== FLAGGED PARCELS ===")
for r in output:
    if r['source'] in ('FRESH',):
        print("  %s | %s" % (r['apn_dash'], r.get('net_assessed_value', 'NO VALUE')))

# Check the 2 that were missing from index
print("\n=== 2 PREVIOUSLY MISSING FROM INDEX ===")
for apn in ('033-067-003-000', '066-420-011-000'):
    r = results.get(apn.replace('-', ''), {})
    if r:
        print("  %s: AsrPrint OK -> doc=%s val=%s" % (apn, r.get('doc_number','?'), r.get('assessed_value','?')))
    else:
        print("  %s: Not in AsrPrint" % apn)
