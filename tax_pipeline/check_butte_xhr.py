import requests, re, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
})

# First, visit the search page to get cookies/session
search_url = 'https://common2.mptsweb.com/MBC/butte/tax/search?f=Q&Asmt=002271003000&TaxYear=2025&RollYear='
r1 = s.get(search_url, timeout=15)

# Now check what cookies were set
print(f"Search page: {r1.status_code}, {len(r1.text)} bytes")
print(f"Cookies: {dict(s.cookies)}")

# Now look for the data-search-url attribute and try to get JSON with XHR headers
# The form has data-search-url="http://common2.mptsweb.com/MBC/butte/tax/search"
# Let me try POST to /MBC/butte/tax/search with XHR headers

s.headers.update({
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Referer': search_url,
})

# Try POST with form data
data = {
    'f': 'Q',
    'Asmt': '002271003000',
    'TaxYear': '2025',
    'RollYear': '',
}
r2 = s.post('https://common2.mptsweb.com/MBC/butte/tax/search', data=data, timeout=15)
print(f"\nPOST search: {r2.status_code}, {len(r2.text)} bytes, Content-Type: {r2.headers.get('Content-Type')}")
print(f"Body preview: {r2.text[:300]}")

# Try GET with XHR headers
r3 = s.get(search_url, timeout=15)
print(f"\nGET with XHR: {r3.status_code}, {len(r3.text)} bytes, CT: {r3.headers.get('Content-Type')}")
print(f"Body preview: {r3.text[:300]}")

# Try fetching the detail page with XHR headers
detail_url = 'https://common2.mptsweb.com/MBC/butte/tax/main/002271003000/2025/0000'
r4 = s.get(detail_url, timeout=15)
print(f"\nDetail page: {r4.status_code}, {len(r4.text)} bytes")
# Check for JSON in detail page
for m in re.finditer(r'sessionStorage\.getItem\([\"\']([^\"\']+)[\"\']', r4.text):
    print(f"  sessionStorage key: {m.group(1)}")
# Check for API endpoints
for m in re.finditer(r'(https?://[^"\']+(?:json|search|api)[^"\']*)', r4.text, re.I):
    url = m.group(1)
    if len(url) < 150 and '/tax/' in url:
        print(f"  API URL: {url}")
