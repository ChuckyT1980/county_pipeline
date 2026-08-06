import requests, re

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

# Get search page and examine ALL script/API references
url = 'https://common2.mptsweb.com/MBC/butte/tax/search?f=Q&Asmt=002271003000&TaxYear=2025&RollYear='
r = s.get(url, timeout=15)
text = r.text

# Find all form actions, data attributes, and API-like strings
print("=== Forms ===")
for m in re.finditer(r'<form[^>]*action=["\']([^"\']*)["\']', text):
    print(f"  action={m.group(1)[:100]}")

print("\n=== data-* attributes with url/search/api ===")
for line in text.split('\n'):
    if 'data-' in line and ('url' in line.lower() or 'api' in line.lower() or 'search' in line.lower()):
        clean = re.sub(r'<[^>]+>', ' ', line).strip()
        clean = re.sub(r'\s+', ' ', clean)
        if clean and len(clean) < 250:
            print(f"  {clean[:200]}")

print("\n=== All data-* attributes ===")
for m in re.finditer(r'data-(\w+)=["\']([^"\']+)["\']', text):
    print(f"  data-{m.group(1)} = {m.group(2)[:100]}")

print("\n=== Content after /tax/ ===")
for m in re.finditer(r'/tax/[a-z]+[^"\']+', text):
    v = m.group()[:120]
    if v not in ['/tax/css/main.css', '/tax/css/main2.css', '/tax/css/print.css']:
        print(f"  {v}")

# Check for QuickSearch URL patterns
print("\n=== QuickSearch / searchUrl ===")
for line in text.split('\n'):
    if 'quickSearch' in line.lower() or 'searchUrl' in line or 'url' in line.lower():
        clean = re.sub(r'<[^>]+>', ' ', line).strip()
        clean = re.sub(r'\s+', ' ', clean)
        if clean and len(clean) < 200 and len(clean) > 10:
            print(f"  {clean}")
