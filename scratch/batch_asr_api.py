"""Batch check APNs via ASR API to find those with owner names"""
import requests, json

# Our 12 Shasta export APNs
export_apns = [
    '070-050-072-000',
    '018-600-041-000',
    '057-180-029-000',
    '083-141-039-000',
    '094-160-031-000',
    '110-140-029-000',
    '005-460-014-000',
    '009-410-016-000',
    '068-430-019-000',
    '119-270-054-000',
    '032-140-010-000',
    '056-230-017-000',
]

# Also try some PDF-matched APNs
pdf_apns = [
    '057-520-007-000',  # from PDFs
    '105-540-015-000',
    '093-131-003-000',
]

base_api = 'https://common1.mptsweb.com/mbap/shasta/idfeeparcel/'
headers = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://common1.mptsweb.com/mbap/shasta/asr'
}

results = []
for apn_dashed in export_apns + pdf_apns:
    clean = apn_dashed.replace('-', '')
    url = f"{base_api}{clean}"
    try:
        r = requests.get(url, timeout=30, headers=headers)
        if r.status_code == 200:
            # Parse the JSON (it's double-encoded)
            text = r.text.strip()
            # Response is a JSON string containing escaped JSON
            inner = json.loads(text)  # first parse: unescape the outer string
            data = json.loads(inner)  # second parse: actual JSON object
            row = data.get('Table', {}).get('Row', {})
            is_show = row.get('IsShowAddress', '')
            owner = row.get('Owner', 'N/A')
            situs = row.get('SitusAddr', 'N/A')
            asmt_status = row.get('AsmtStatus', '')
            
            results.append({
                'apn': apn_dashed,
                'is_show_address': is_show,
                'owner': owner,
                'situs': situs,
                'status': asmt_status
            })
            print(f"{apn_dashed}: IsShowAddress={is_show}, Owner={owner[:50] if owner != 'N/A' else owner}, Situs={situs[:50]}")
        else:
            print(f"{apn_dashed}: HTTP {r.status_code}")
    except Exception as e:
        print(f"{apn_dashed}: Error {e}")

print("\n\n=== Results with owner names ===")
for r in results:
    if r['owner'] != 'N/A' and r['owner']:
        print(f"  {r['apn']}: {r['owner']}")

print("\n=== Summary ===")
total = len(results)
with_owner = sum(1 for r in results if r['owner'] != 'N/A' and r['owner'])
show_address = sum(1 for r in results if r['is_show_address'] == '1')
print(f"Total: {total}, With owner: {with_owner}, Show address: {show_address}")
