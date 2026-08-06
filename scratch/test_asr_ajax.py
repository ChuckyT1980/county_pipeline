"""Try ASR search via AJAX/API calls with different APN formats"""
import requests, json, time

base = 'https://common1.mptsweb.com/mbap/shasta/asr'
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json, text/plain, */*'})

# Get the page first for cookies and tokens
r = session.get(base, timeout=30)
print(f"GET {base}: {r.status_code}")
print(f"Cookies: {dict(session.cookies)}")

# Look for RequestVerificationToken
import re
token = ''
for m in re.findall(r'__RequestVerificationToken.*?value="([^"]*)"', r.text):
    token = m
    print(f"Token found: {token[:50]}...")
    break

# Look for API endpoints in JS
for m in re.findall(r'data-search-url="([^"]*)"', r.text):
    print(f"Search URL: {m}")

# Look for URLs in scripts
for m in re.findall(r'(?:url|api|search|lookup)\s*[:=]\s*["\']([^"\']+)["\']', r.text, re.I):
    print(f"JS URL: {m}")

# Try the tax search API instead (different system)
print("\n--- Trying Tax Search API ---")
tax_url = 'https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/070050072000'
try:
    r2 = session.get(tax_url, timeout=30, headers={'Referer': 'https://common2.mptsweb.com/'})
    print(f"Tax API: {r2.status_code}")
    print(f"Response: {r2.text[:500]}")
except Exception as e:
    print(f"Tax API error: {e}")

# Try without dashes
clean_apn = '070050072000'
print(f"\n--- Trying Tax Search API with clean APN: {clean_apn} ---")
tax_url2 = f'https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/{clean_apn}'
try:
    r3 = session.get(tax_url2, timeout=30, headers={'Referer': 'https://common2.mptsweb.com/'})
    print(f"Tax API: {r3.status_code}")
    print(f"Response: {r3.text[:500]}")
except Exception as e:
    print(f"Tax API error: {e}")

# Try ASR search via AJAX endpoint
print("\n--- Trying ASR Search API ---")
asr_search_url = 'https://common1.mptsweb.com/mbap/shasta/asr/search'
try:
    r4 = session.post(asr_search_url, json={
        'searchType': 'idfeeparcel',
        'searchValue': '070050072000'
    }, timeout=30, headers={'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'})
    print(f"ASR Search: {r4.status_code}")
    print(f"Response: {r4.text[:1000]}")
except Exception as e:
    print(f"ASR Search error: {e}")

# Try with form data instead
print("\n--- Trying ASR form POST ---")
form_url = 'https://common1.mptsweb.com/mbap/shasta/asr'
try:
    r5 = session.post(form_url, data={
        'SearchVal': 'idfeeparcel',
        'SearchValue': '070050072000',
        '__RequestVerificationToken': token
    }, timeout=60, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    print(f"Form POST: {r5.status_code}")
    # Check if results or same page
    if 'connection timed out' in r5.text.lower():
        print("TIMEOUT - same error")
    elif '070-050-072' in r5.text or 'property' in r5.text.lower() and len(r5.text) > 2000:
        print(f"Got results! Length: {len(r5.text)}")
        # Extract owner info
        for line in r5.text.split('\n'):
            if any(kw in line.lower() for kw in ['owner', 'name', 'taxpayer']):
                print(f"  NAME LINE: {line.strip()[:200]}")
        # Save result
        with open('scratch/asr_form_result.html', 'w') as f:
            f.write(r5.text)
    else:
        print(f"Unknown result. Length: {len(r5.text)}")
        with open('scratch/asr_form_result2.html', 'w') as f:
            f.write(r5.text)
except Exception as e:
    print(f"Form POST error: {e}")
