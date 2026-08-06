"""Find the ASR API URL parameters"""
import requests, re

r = requests.get('https://common1.mptsweb.com/mbap/shasta/asr', timeout=30, headers={'User-Agent': 'Mozilla/5.0'})

# Find appFolder
for m in re.findall(r"appFolder\s*[=:]\s*['\"]([^'\"]+)['\"]", r.text):
    print(f"appFolder = {m}")

for m in re.findall(r"countyname\s*[=:]\s*['\"]([^'\"]+)['\"]", r.text):
    print(f"countyname = {m}")

# Also check for base URL
for m in re.findall(r"baseurl\s*[=:]\s*['\"]([^'\"]+)['\"]", r.text, re.I):
    print(f"baseurl = {m}")

# Now try the API call
appFolder = '/mbap/'
countyname = 'shasta'
searchType = 'idfeeparcel'
searchValue = '070050072000'

api_url = f"https://common1.mptsweb.com{appFolder}{countyname}/{searchType}/{searchValue}"
print(f"\nTrying API URL: {api_url}")

r2 = requests.get(api_url, timeout=30, headers={
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json, text/plain, */*',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://common1.mptsweb.com/mbap/shasta/asr'
})
print(f"Status: {r2.status_code}")
print(f"Content-Type: {r2.headers.get('Content-Type', '')}")
print(f"Response ({len(r2.text)} chars):")
print(r2.text[:2000])

# Save full response
with open('scratch/asr_api_response.json', 'w') as f:
    f.write(r2.text)
