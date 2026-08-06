import re, json

with open('bid4assets_butte_aug2026.html', encoding='utf-8') as f:
    html = f.read()

# Find the Data array in the page
idx = html.find('"Data":[')
if idx < 0:
    print("No Data section found")
    exit()

# Extract the data JSON
depth = 0
in_str = False
esc = False
start = idx + 7
for i in range(start, min(start + 100000, len(html))):
    c = html[i]
    if esc:
        esc = False
        continue
    if c == '\\':
        esc = True
        continue
    if c == '"':
        in_str = not in_str
        continue
    if in_str:
        continue
    if c == '[':
        depth += 1
    elif c == ']':
        depth -= 1
        if depth == 0:
            data_json = html[idx:start] + html[start:i+1]
            break

try:
    data = json.loads(data_json)
except:
    # Try cleaning escape sequences
    clean = data_json.replace('\\"', "'").replace('\\\\', '\\')
    try:
        data = json.loads(clean)
    except:
        print("JSON parse failed, trying regex extraction")
        data = None

if data:
    records = data.get('Data', [])
    print("Records found: %d" % len(records))
    for r in records:
        apn = r.get('APN', '') or r.get('ParcelNumber', '') or r.get('PropertyID', '')
        address = r.get('Address', '') or r.get('PropertyAddress', '')
        min_bid = r.get('MinBid', '') or r.get('MinimumBid', '') or r.get('OpeningBid', '')
        print("  %s | %s | %s" % (apn, address, min_bid))
else:
    # Extract APNs directly from raw text
    apns = re.findall(r'\d{3}-\d{3}-\d{3}-\d{3}', data_json)
    print("APNs extracted via regex: %d" % len(apns))
    for a in sorted(set(apns)):
        print(" ", a)
