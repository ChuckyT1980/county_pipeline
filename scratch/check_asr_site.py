"""Check the Shasta Assessment Inquiry (ASR) site for owner names"""
import requests, re, json

url = 'https://common1.mptsweb.com/mbap/shasta/asr'
r = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
print(f'Status: {r.status_code}')
print(f'URL: {r.url}')
print(f'Length: {len(r.text)}')

# Save first 5000 chars to inspect
with open('scratch/asr_page.html', 'w') as f:
    f.write(r.text[:5000])

# Look for form fields
inputs = re.findall(r'<input[^>]*>', r.text)
for inp in inputs:
    il = inp.lower()
    if any(kw in il for kw in ['search', 'parcel', 'apn', 'fee', 'submit', 'text']):
        print(f'  INPUT: {inp[:250]}')

# Look for selects
selects = re.findall(r'<select[^>]*>.*?</select>', r.text, re.DOTALL)
for sel in selects[:5]:
    print(f'  SELECT: {sel[:300]}')

# Look for owner/name text
for m in re.findall(r'(?:owner|name)[^<]{3,100}', r.text, re.I):
    print(f'  OWNER_TEXT: {m[:120]}')

# Look for links
for m in re.findall(r'href=[\'"]([^\'"]*)[\'"]', r.text):
    if any(kw in m.lower() for kw in ['search', 'asr', 'parcel', 'lookup']):
        print(f'  LINK: {m}')
