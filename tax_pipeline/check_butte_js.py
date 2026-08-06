import requests, re

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

url = 'https://common2.mptsweb.com/MBC/bundles/customscripts?v=VrOFyGdxNeAHHR6fbFdnzMijuS2zLvCboxZ1frPYDxE1'
r = s.get(url, timeout=15)
text = r.text
print(f"Length: {len(text)}")

patterns = [
    (r'url\s*[:=]\s*["\']([^"\']+)["\']', 'URL'),
    (r'/MBC/[^"\';\s]+', 'MBC path'),
    (r'sessionStorage', 'sessionStorage'),
    (r'SearchResults', 'SearchResults'),
    (r'Owner', 'Owner'),
    (r'ajax\(', 'ajax call'),
    (r'setItem', 'setItem'),
]

for pat, label in patterns:
    matches = re.findall(pat, text, re.IGNORECASE)
    unique = set(str(m)[:120] for m in matches if len(str(m)) > 3)
    if unique:
        print(f"\n=== {label} ({len(unique)}) ===")
        for m in list(unique)[:10]:
            print(f"  {m}")
