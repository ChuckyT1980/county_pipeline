"""
Fix 3 remaining auction parcels:
  1. 033-067-003-000 (OWENS, JIMMIE R) - doc=2005R0005032
  2. 066-420-011-000 (BATES REVOCABLE INT VIV TRUST) - doc=2018ID082503
  3. 071-270-029-000/990-322-648-000 - combined APN, already in enriched data

Also produce final clean CSV.
"""
import csv, requests, concurrent.futures
from bs4 import BeautifulSoup as BS
from playwright.sync_api import sync_playwright
import time

BASE = r"C:\Users\chuck\Downloads\county_pipeline\tax_pipeline"

# === STEP 1: Enrich 033-067-003-000 and 066-420-011-000 ===

MISSING = [
    {'apn': '033-067-003-000', 'asmt12': '033067003000', 'doc': '2005R0005032', 'min_bid': 5802},
    {'apn': '066-420-011-000', 'asmt12': '066420011000', 'doc': '2018ID082503', 'min_bid': 5762},
]

def recorder_doc_search(doc_number):
    """Search Butte recorder by doc number -> grab grantee"""
    docs = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://recorder.buttecounty.net/recorder/websearch/", timeout=20000)
            page.wait_for_load_state("networkidle")
            
            # Enter document number
            page.fill("#DocNumber", doc_number)
            page.click("#searchButton")
            page.wait_for_timeout(2000)
            
            # Parse results
            for li in page.query_selector_all("li[class*=ui-li]"):
                text = li.inner_text()
                doc = {
                    'type': '',
                    'grantor': '',
                    'grantee': '',
                    'date': '',
                }
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    l = line.strip()
                    if 'Doc Type:' in l:
                        doc['type'] = l.replace('Doc Type:', '').strip()
                    elif 'Grantor' in l or 'Grantor/Grantee' in l:
                        if i+1 < len(lines):
                            doc['grantor'] = lines[i+1].strip()
                    elif 'Grantee' in l:
                        if i+1 < len(lines):
                            doc['grantee'] = lines[i+1].strip()
                    elif i == 0 and l:
                        doc['date'] = l
                docs.append(doc)
            browser.close()
    except Exception as e:
        return [{'error': str(e)}]
    return docs

def name_search(name, max_results=5):
    """Search recorder by owner/party name -> return document types and liens"""
    docs = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://recorder.buttecounty.net/recorder/websearch/", timeout=20000)
            page.wait_for_load_state("networkidle")
            
            page.fill("#SearchName", name)
            page.click("#searchButton")
            page.wait_for_timeout(2000)
            
            count = 0
            for li in page.query_selector_all("li[class*=ui-li]"):
                if count >= max_results:
                    break
                text = li.inner_text()
                doc = {'type': '', 'date': ''}
                lines = text.split('\n')
                for line in lines:
                    l = line.strip()
                    if 'Doc Type:' in l:
                        doc['type'] = l.replace('Doc Type:', '').strip()
                    elif l and 'Doc Type:' not in l and 'Grantor' not in l and 'Grantee' not in l and l != '':
                        if not doc['date']:
                            # First substantial line is usually date/doc#
                            doc['date'] = l[:30]
                docs.append(doc)
                count += 1
            browser.close()
    except Exception as e:
        return [{'error': str(e)}]
    return docs

def categorize_doc_type(dt):
    dt = dt.upper()
    if 'ASSIGNMENT' in dt and 'RENT' in dt:
        return 'assignment_of_rents'
    if 'NOTICE' in dt and 'DEFAULT' in dt:
        return 'notice_of_default'
    if 'TRUSTEE' in dt and ('DEED' in dt or 'SALE' in dt):
        return 'trustee_deed'
    if 'LIS PENDENS' in dt:
        return 'lis_pendens'
    if 'ABSTRACT' in dt:
        return 'abstract_of_judgment'
    if 'TAX LIEN' in dt:
        return 'tax_lien'
    if 'MORTGAGE' in dt or 'DEED OF TRUST' in dt:
        return 'mortgage'
    if 'MECHANIC' in dt or 'MECHANICS' in dt:
        return 'mechanic_lien'
    if 'DELINQUENT' in dt:
        return 'delinquent_assessment'
    if 'JUDGMENT' in dt:
        return 'judgment'
    return None

def quick_score(docs):
    """Simplified scoring from recorder docs"""
    score = 0
    types = set()
    for d in docs:
        ct = categorize_doc_type(d.get('type', ''))
        if ct:
            types.add(ct)
    if 'assignment_of_rents' in types: score += 28
    if 'notice_of_default' in types: score += 25
    if 'mortgage' in types: score += 20
    if 'abstract_of_judgment' in types: score += 5
    if 'lis_pendens' in types: score += 3
    if 'tax_lien' in types: score += 3
    if 'trustee_deed' in types: score += 10
    if 'mechanic_lien' in types: score += 3
    return score, types

results = {}
for m in MISSING:
    print("\n=== Enriching %s ===" % m['apn'])
    
    # Step 2: Recorder doc search
    docs = recorder_doc_search(m['doc'])
    print("  Doc search: %d results" % len(docs))
    
    # Extract grantee
    grantee = ''
    for d in docs:
        if d.get('grantee') and not d.get('error'):
            g = d['grantee'].strip()
            if g and len(g) > 3 and g not in ('View', 'Export as CSV', 'Link'):
                grantee = g
                break
    
    print("  Grantee: %s" % (grantee or 'NONE'))
    
    # Step 3: Name search for liens/mortgages
    # Use grantee if found, otherwise use doc type search if available
    party_name = grantee if grantee else None
    
    all_docs = []
    if party_name:
        # Try last name only for broader search
        last_name = party_name.split(',')[0].strip()
        print("  Name search for: %s" % last_name)
        name_docs = name_search(last_name, max_results=10)
        print("  Name search: %d results" % len(name_docs))
        all_docs = name_docs
    
    # Score
    score, types_found = quick_score(all_docs)
    print("  Score: %d (types: %s)" % (score, types_found))
    
    results[m['apn']] = {
        'grantee': grantee,
        'score': score,
        'doc_types': types_found,
        'doc_count': len(all_docs),
    }

# === STEP 2: Load the enriched CSV and fix ===
print("\n\n=== Fixing final CSV ===")

rows = []
with open(BASE + '/butte_auction_all_105_enriched.csv', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        apn = row['apn_dash']
        
        # Fix 033-067-003-000
        if apn == '033-067-003-000' and results.get('033-067-003-000'):
            r = results['033-067-003-000']
            row['score'] = str(r['score'])
            row['owner_name'] = r['grantee'] if r['grantee'] else 'OWENS, JIMMIE R'
            row['total_open_mortgages'] = '0'
            row['open_lien_types'] = '; '.join(sorted(r['doc_types']))
            row['has_assignment_of_rents'] = 'True' if 'assignment_of_rents' in r['doc_types'] else 'False'
            row['notice_of_default_present'] = 'True' if 'notice_of_default' in r['doc_types'] else 'False'
            row['has_trustee_deed'] = 'True' if 'trustee_deed' in r['doc_types'] else 'False'
            row['recorder_doc_count'] = str(r['doc_count'])
            row['source'] = 'NEWLY_ENRICHED'
            print("  Fixed %s: score=%d grantee=%s" % (apn, r['score'], r['grantee']))
        
        # Fix 066-420-011-000
        if apn == '066-420-011-000' and results.get('066-420-011-000'):
            r = results['066-420-011-000']
            row['score'] = str(r['score'])
            row['owner_name'] = r['grantee'] if r['grantee'] else 'BATES REVOCABLE INT VIV TRUST ESTATE'
            row['total_open_mortgages'] = '0'
            row['open_lien_types'] = '; '.join(sorted(r['doc_types']))
            row['has_assignment_of_rents'] = 'True' if 'assignment_of_rents' in r['doc_types'] else 'False'
            row['notice_of_default_present'] = 'True' if 'notice_of_default' in r['doc_types'] else 'False'
            row['has_trustee_deed'] = 'True' if 'trustee_deed' in r['doc_types'] else 'False'
            row['recorder_doc_count'] = str(r['doc_count'])
            row['source'] = 'NEWLY_ENRICHED'
            print("  Fixed %s: score=%d grantee=%s" % (apn, r['score'], r['grantee']))
        
        # Fix 071-270-029-000 combined APN - remove the mangled duplicate
        # The mangled row has source=='FRESH' and no score
        # The real enriched row has source like 'NEWLY_ENRICHED' or 'ALREADY_ENRICHED'
        if apn == '071-270-029-000' and row.get('source') == 'FRESH':
            print("  Removing mangled duplicate: %s" % apn)
            continue  # Skip this row - the real enriched one was already processed
        
        rows.append(row)

# Sort by score desc then APN
rows.sort(key=lambda r: (0 - int(r['score']) if r['score'] and r['score'].isdigit() else -9999, r['apn_dash']))

with open(BASE + '/butte_auction_all_105_enriched.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)

print("\n=== DONE ===")
print("Total rows: %d" % len(rows))

scores = [int(r['score']) for r in rows if r['score'] and r['score'].isdigit()]
print("Score >= 80: %d" % len([s for s in scores if s >= 80]))
print("Score 50-79: %d" % len([s for s in scores if 50 <= s < 80]))
print("Score 25-49: %d" % len([s for s in scores if 25 <= s < 50]))
print("Score 0-24:  %d" % len([s for s in scores if s < 25]))

# Check all APNs present
apns_set = set(r['apn_dash'] for r in rows)
print("\nUnique APNs: %d" % len(apns_set))
