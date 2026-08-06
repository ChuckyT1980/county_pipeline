import requests, re

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
url = 'https://common2.mptsweb.com/MBC/butte/tax/search?f=Q&Asmt=002271003000&TaxYear=2025&RollYear='
r = s.get(url, timeout=15)
text = r.text
lines = text.split('\n')

# Show inputs, hidden fields, inline scripts
for i, line in enumerate(lines):
    s = line.strip()
    if '<input' in s or '<button' in s or 'type="hidden"' in s:
        clean = re.sub(r'<[^>]+>', ' ', s).strip()
        clean = re.sub(r'\s+', ' ', clean)
        if clean and len(clean) < 200:
            print(f"INPUT: {clean}")
    if '<script' in s and '</script>' in s and 'src' not in s:
        clean = re.sub(r'<[^>]+>', ' ', s).strip()
        clean = re.sub(r'\s+', ' ', clean)
        if clean:
            print(f"INLINE: {clean[:200]}")

# Also look for viewstate / eventvalidation (ASP.NET patterns)
print("\n=== ASP.NET ===")
for m in re.finditer(r'id="__[^"]*"\s+value="([^"]*)"', text):
    print(f"  {m.group()[:100]}")

# Look for the search form
print("\n=== Search form ===")
for m in re.finditer(r'<form[^>]*>', text):
    form = m.group()
    if 'id' in form or 'action' in form:
        print(f"  {form}")
