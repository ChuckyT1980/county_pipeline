"""Find the ASR search API endpoint from the page JavaScript"""
import requests, re, json

r = requests.get('https://common1.mptsweb.com/mbap/shasta/asr', timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
print(f"Status: {r.status_code}")

# Find scripts
for m in re.findall(r'src=[\'"]([^\'"]*\.js[^\'"]*)[\'"]', r.text):
    print(f"JS: {m}")

# Find inline scripts
scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
print(f"\nFound {len(scripts)} inline scripts")
for i, s in enumerate(scripts):
    if len(s.strip()) > 50:
        # Look for search/API calls
        for m in re.findall(r'(?:url|api|search|fetch|ajax|post|get)\s*[:=]\s*[\'"]([^\'"]+)[\'"]', s, re.I):
            print(f"  Script {i}: URL found: {m}")
        for m in re.findall(r'\$.post\([\'"]([^\'"]+)[\'"]', s):
            print(f"  Script {i}: $.post: {m}")
        for m in re.findall(r'\$.ajax\([\'"]([^\'"]+)[\'"]', s):
            print(f"  Script {i}: $.ajax: {m}")
        # Look for window.location or form action
        for m in re.findall(r'action=[\'"]([^\'"]*search[^\'"]*)[\'"]', r.text, re.I):
            print(f"  Form action: {m}")

# Also check what the Search button links to
for m in re.findall(r'Search[^<]*</a>', r.text):
    hrefs = re.findall(r'href=[\'"]([^\'"]*)[\'"]', m)
    if hrefs:
        print(f"  Search link: {hrefs[0]}")
