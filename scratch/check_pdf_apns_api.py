"""Check PDF-matched APNs via ASR API - do they return Owner field?"""
import requests, json

# Load PDF owners
pdf_owners = json.load(open('scratch/shasta_pdf_owners.json'))
apns = list(pdf_owners.keys())[:30]  # Check first 30

base_api = 'https://common1.mptsweb.com/mbap/shasta/idfeeparcel/'
headers = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://common1.mptsweb.com/mbap/shasta/asr'
}

matches = []
for apn in apns:
    clean = apn.replace('-', '')
    url = f"{base_api}{clean}"
    try:
        r = requests.get(url, timeout=30, headers=headers)
        if r.status_code == 200:
            text = r.text.strip()
            inner = json.loads(text)
            data = json.loads(inner)
            row = data.get('Table', {}).get('Row')
            if row:
                is_show = row.get('IsShowAddress', '?')
                owner = row.get('Owner', 'N/A')
                situs = row.get('SitusAddr', 'N/A')
                pdf_name = pdf_owners[apn]
                match_owner = (owner != 'N/A' and owner.upper().strip() == pdf_name.upper().strip()[:50])
                matches.append({
                    'apn': apn,
                    'is_show': is_show,
                    'api_owner': owner if owner != 'N/A' else '',
                    'pdf_owner': pdf_name,
                    'match': match_owner
                })
                print(f"{apn}: is_show={is_show} api_owner={str(owner)[:40]:40s} pdf_owner={pdf_name[:40]:40s} match={match_owner}")
            else:
                print(f"{apn}: No row data (null)")
        else:
            print(f"{apn}: HTTP {r.status_code}")
    except Exception as e:
        print(f"{apn}: Error {e}")

print(f"\n\nChecked {len(matches)} APNs")
show_address = sum(1 for m in matches if m['is_show'] == '1')
show_owner = sum(1 for m in matches if m['is_show'] == '0')
with_owner_field = sum(1 for m in matches if m['api_owner'])
matches_found = sum(1 for m in matches if m['match'])
print(f"IsShowAddress=1: {show_address}, IsShowAddress=0: {show_owner}")
print(f"With Owner field: {with_owner_field}")
print(f"Matches PDF: {matches_found}")

# Save results
with open('scratch/apn_api_comparison.json', 'w') as f:
    json.dump(matches, f, indent=2)
