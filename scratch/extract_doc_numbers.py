"""Extract Document Numbers from MBC detail pages for the 12 Shasta export leads"""
import requests, re, time, json
from pathlib import Path
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
})

# The 12 Shasta export leads APNs
apns = [
    '070-050-072-000', '064-100-031-000', '018-600-041-000',
    '102-150-007-000', '097-150-016-000', '055-250-028-000',
    '085-050-022-000', '114-300-021-000', '102-450-028-000',
    '060-250-053-000', '060-050-036-000', '107-300-018-000',
]

doc_numbers = {}
for apn in apns:
    compact = apn.replace('-', '')
    url = 'https://common2.mptsweb.com/MBC/shasta/tax/main/%s/2025/0000' % compact
    try:
        resp = session.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find Document Number in the text
        text = soup.get_text(separator='\n')
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        doc_num = None
        for i, line in enumerate(lines):
            if 'Document Number' in line:
                # Next non-empty line should be the number
                for j in range(i, min(i+3, len(lines))):
                    candidate = lines[j]
                    if candidate and candidate != line and not candidate.startswith('Document'):
                        doc_num = candidate
                        break
                break
        
        if doc_num:
            doc_numbers[apn] = doc_num
            print('  %s -> Doc# %s' % (apn, doc_num))
        else:
            # Try looking at the Assessment Info section
            dt_tags = soup.find_all('dt')
            for dt in dt_tags:
                if 'Document' in dt.get_text():
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        doc_num = dd.get_text(strip=True)
                        doc_numbers[apn] = doc_num
                        print('  %s -> Doc# %s (from dt/dd)' % (apn, doc_num))
                        break
            
            if not doc_num:
                print('  %s -> NO DOC NUMBER FOUND' % apn)
    except Exception as e:
        print('  %s -> ERROR: %s' % (apn, e))
    
    time.sleep(0.5)

print('\n=== Summary ===')
for apn, doc in doc_numbers.items():
    print('  %s -> %s' % (apn, doc))
print('Total with doc numbers: %d / %d' % (len(doc_numbers), len(apns)))

with open(Path(__file__).parent / 'shasta_export_doc_numbers.json', 'w') as f:
    json.dump(doc_numbers, f, indent=2)
