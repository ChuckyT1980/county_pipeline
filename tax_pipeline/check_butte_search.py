import requests, re, json

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

# The search URL pattern from the book CSV files
search_url = 'https://common2.mptsweb.com/MBC/butte/tax/search?f=Q&Asmt=002271003000&TaxYear=2025&RollYear='
print(f"Fetching: {search_url}")
r = s.get(search_url, timeout=20)
text = r.text
print(f"Status: {r.status_code}, Length: {len(text)}")

# Look for the data source - either inline JSON or AJAX call
for line in text.split('\n'):
    s_line = line.strip()
    if 'SearchResults' in s_line or 'setItem' in s_line or 'Owner' in s_line:
        print(f"  MATCH: {s_line[:200]}")
    if 'api' in s_line.lower() or 'json' in s_line.lower() or 'fetch' in s_line.lower() or 'ajax' in s_line.lower():
        if any(x in s_line for x in ['url', 'source', 'data', 'href', 'src']) and len(s_line) < 300:
            print(f"  API: {s_line[:200]}")

# Check for embedded JSON-LD or script data
for m in re.finditer(r'<script[^>]*>\s*var\s+\w+\s*=\s*(\[.*?\])\s*;</script>', text, re.DOTALL):
    print(f"Found JS array: {m.group(1)[:200]}")

# Check for JSON.parse usages
for m in re.finditer(r'JSON\.parse\([^)]+\)', text):
    print(f"JSON.parse found: {m.group()[:200]}")

# Check for any inline JSON data
for m in re.finditer(r'"Owner"\s*:\s*"[^"]+"', text):
    print(f"Owner found: {m.group()[:150]}")
