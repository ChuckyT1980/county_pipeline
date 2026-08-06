import requests, re
from bs4 import BeautifulSoup

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

url = "https://apps.mptsweb.com/TaxBillv2/Default.aspx?County=shasta&Asmt=070050072000&TaxYear=2025&RollCat=CS&RollYr=&RollType=S&DisplayType=HTML"
resp = session.get(url, timeout=15)

# Search raw HTML for assessed value patterns
text = resp.text
print(f"Page size: {len(text)} bytes")

# Find all numbers that look like dollar values
amounts = re.findall(r'(?:\$)?[\d,]+\.\d{2}', text)
print(f"\nDollar amounts found: {len(amounts)}")
# Show unique amounts sorted
unique = sorted(set(amounts), key=lambda x: float(x.replace(',','').replace('$','')), reverse=True)
for a in unique[:20]:
    print(f"  {a}")

# Search for assessment-related text snippets
for kw in ['NET TAXABLE VALUE', 'LAND', 'IMPROVEMENT', 'ASSESSED VALUE', 'EXEMPTION', 'TRA 1002']:
    indices = [m.start() for m in re.finditer(kw, text.upper())]
    if indices:
        for idx in indices[:3]:
            snippet = text[max(0,idx-50):idx+100]
            # clean
            snippet = ' '.join(snippet.split())
            print(f"\n  Found '{kw}' at {idx}: ...{snippet}...")
    else:
        print(f"\n  '{kw}' not found")

# Look specifically for the net assessed value near TRA
idx = text.find('TRA')
if idx >= 0:
    print(f"\n\n=== Content around TRA ===")
    for i in range(-1, 2):
        snippet = text[idx + i*2000:idx + i*2000 + 2000]
        snippet = ' '.join(snippet.split())
        print(f"\n  Block {i}: {snippet[:500]}")
