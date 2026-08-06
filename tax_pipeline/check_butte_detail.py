import requests, re, json

url = 'https://common2.mptsweb.com/MBC/butte/tax/main/002271003000/2025/0000'
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
r = s.get(url, timeout=20)
text = r.text

# Search for API endpoints or JSON data URLs
patterns = [
    r'fetch\([^)]+\)',
    r'url["\']?\s*[:=]\s*["\']([^"\']+(?:json|api)[^"\']*)["\']',
    r'data-url\s*=\s*"([^"]+)"',
    r'/api/[^"\']*',
    r'ajax\([^)]+\)',
]

print("=== API/URL patterns ===")
for p in patterns:
    matches = re.findall(p, text, re.IGNORECASE)
    for m in matches:
        s = str(m).strip()
        if len(s) > 10:
            print(f"  {s[:150]}")

# Find JavaScript variables
print("\n=== JS variable assignments ===")
for line in text.split('\n'):
    s = line.strip()
    if any(x in s for x in ['var ', 'let ', 'const ']) and ('Asmt' in s or 'Owner' in s or 'search' in s.lower()):
        print(f"  {s[:200]}")

# Look for the page's JS file reference
print("\n=== Script sources ===")
for m in re.finditer(r'<script[^>]*src=["\']([^"\']+)["\']', text):
    print(f"  {m.group(1)[:150]}")

# Check for inline JSON data
print("\n=== JSON-like data ===")
for m in re.finditer(r'\{[^{}]*"Asmt"[^{}]*\}', text):
    try:
        data = json.loads(m.group())
        print(f"  {json.dumps(data)[:200]}")
    except:
        pass

# Try to find Owner name patterns specifically in the search results data
# The template uses v.Owner so there must be a JSON data source somewhere
print("\n=== Owner references ===")
for line in text.split('\n'):
    if '"Owner"' in line or "'Owner'" in line:
        print(f"  {line.strip()[:200]}")
