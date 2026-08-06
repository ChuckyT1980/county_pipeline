import requests, re, csv
from bs4 import BeautifulSoup

def normalize_parcel(raw):
    return re.sub(r"[^0-9]", "", raw.strip())

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

apn = "070-050-072-000"
parcel = normalize_parcel(apn)
tax_url = f"https://common2.mptsweb.com/MBC/shasta/tax/main/{parcel}/2025/0000"

resp = session.get(tax_url, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Find all links/iframes/scripts
print("=== Links ===")
for a in soup.find_all('a'):
    href = a.get('href', '')
    text = a.get_text(strip=True)
    if href and not href.startswith('#') and not href.startswith('javascript'):
        print(f"  {text:40s} -> {href}")

print("\n=== Iframes ===")
for iframe in soup.find_all('iframe'):
    src = iframe.get('src', '')
    print(f"  src={src}")

print("\n=== Scripts with external src ===")
for script in soup.find_all('script'):
    src = script.get('src', '')
    if src:
        print(f"  {src}")

# Look for assessment-related URLs in the HTML
text = resp.text
# Find all URLs
urls = re.findall(r'(https?://[^\s"\'<>]+)', text)
print("\n=== All URLs in page ===")
for u in urls:
    if any(kw in u.lower() for kw in ['assess', 'value', 'detail', 'ajax', 'api', 'load']):
        print(f"  {u}")

# Try the assessment tab URL pattern
print("\n=== Trying assessment tab URLs ===")
for tab_path in ['/assessment', '/asr', '/asr/main', '/detail', '/asr/detail']:
    url = f"https://common2.mptsweb.com/MBC/shasta{tab_path}/{parcel}/2025/0000"
    r = session.get(url, timeout=10)
    print(f"  {url}: HTTP {r.status_code} ({len(r.text)} bytes)")
