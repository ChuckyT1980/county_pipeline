import csv
from collections import Counter

s = list(csv.DictReader(open('tax_pipeline/shasta_MASTER_leads_with_liens.csv', newline='', encoding='utf-8-sig')))
print("=== SHASTA ===")
for col in ['asrprint_status','regrid_status','owner_source','taxbill_status']:
    print(f'{col}: {dict(Counter(r.get(col,"") for r in s))}')

t = list(csv.DictReader(open('tax_pipeline/tehama_MASTER_leads_with_liens.csv', newline='', encoding='utf-8-sig')))
print("\n=== TEHAMA ===")
for col in ['asrprint_status','regrid_status','owner_source','taxbill_status']:
    print(f'{col}: {dict(Counter(r.get(col,"") for r in t))}')

# Check if Shasta asrprint URL is accessible
import requests
print("\n=== Testing Shasta AsrPrint URLs ===")
for r in s[:3]:
    url = r.get('asrprint_url','')
    if url:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        print(f'{r["APN"]}: HTTP {resp.status_code} ({len(resp.text)} bytes)')
