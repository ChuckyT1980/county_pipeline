import re
with open('bid4assets_butte_aug2026.html', encoding='utf-8') as f:
    html = f.read()

# Look for download/export links, CSV, Excel references
for pat in [r'Download', r'Export', r'\.csv', r'\.xlsx', r'Excel', r'spreadsheet', r'property.?list', r'All.?Items']:
    for m in re.finditer(pat, html, re.I):
        start = max(0, m.start()-200)
        end = min(len(html), m.end()+200)
        ctx = html[start:end]
        clean = re.sub(r'<[^>]+>', ' ', ctx)
        clean = re.sub(r'\s+', ' ', clean).strip()
        print('Found "%s": ...%s...' % (pat, clean[:200]))
        break

# Extract all collection names (they contain APN ranges)
collections = re.findall(r'CollectionName["\':]+\s*["\']([^"\']+)["\']', html)
print('\n=== COLLECTION GROUPINGS ===')
for c in collections:
    print(' ', c)

# Also extract storefront collection data more completely
idx = html.find('"Data":[')
if idx > 0:
    depth = 0
    in_str = False
    esc = False
    start = idx + 7
    end = start
    for i in range(start, min(start + 100000, len(html))):
        c = html[i]
        if esc: esc = False; continue
        if c == '\\': esc = True; continue
        if c == '"': in_str = not in_str; continue
        if in_str: continue
        if c == '[': depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    data_str = html[idx:end]
    # Print the full structure
    print('\n=== FULL DATA STRUCTURE ===')
    print(data_str[:5000])
