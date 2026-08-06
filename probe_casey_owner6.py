"""
Probe 6:
1. Download actual Excess Proceeds xlsx from tehama.gov - find APN 305-073-053-000
2. Download Tax Sale list xlsx - find owner names
3. Probe ParcelQuest Tehama (county-endorsed property lookup)
4. Probe the MPTS common3 public inquiry interface
"""
import requests, re, io
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
})

APN = '305-073-053-000'
APN_CLEAN = '305073053000'

# ── 1. Download and inspect the Excess Proceeds worksheet ────────────────────
print('=== EXCESS PROCEEDS XLSX FROM TEHAMA.GOV ===')
ep_url = 'https://www.tehama.gov/wp-content/uploads/2024/01/Excess-Proceeds-Worksheet-23.11.17-v2.xlsx'
try:
    r = s.get(ep_url, timeout=30)
    print(f'Status: {r.status_code}, len={len(r.content)}, ct={r.headers.get("content-type","")}')
    if r.status_code == 200:
        with open('tehama_excess_proceeds_county.xlsx', 'wb') as f:
            f.write(r.content)
        print('Saved to tehama_excess_proceeds_county.xlsx')
        
        import pandas as pd
        df = pd.read_excel(io.BytesIO(r.content), sheet_name=None)
        for sheet_name, sheet_df in df.items():
            print(f'\nSheet: {sheet_name}, rows={len(sheet_df)}, cols={list(sheet_df.columns)[:10]}')
            print(sheet_df.head(3).to_string())
            # Search for our APN
            for col in sheet_df.columns:
                if sheet_df[col].dtype == object:
                    hits = sheet_df[sheet_df[col].astype(str).str.replace('-','').str.strip() == APN_CLEAN]
                    if len(hits) > 0:
                        print(f'*** FOUND APN {APN} in column {col}! ***')
                        print(hits.to_string())
except Exception as e:
    print(f'ERROR: {e}')

print()

# ── 2. Download Tax Sale list xlsx ───────────────────────────────────────────
print('=== TAX SALE LIST XLSX FROM TEHAMA.GOV ===')
ts_url = 'https://www.tehama.gov/wp-content/uploads/2024/03/Tax-Sale-Property-Info-Final-Upload-24.03.04.xlsx'
try:
    r = s.get(ts_url, timeout=30)
    print(f'Status: {r.status_code}, len={len(r.content)}, ct={r.headers.get("content-type","")}')
    if r.status_code == 200:
        with open('tehama_tax_sale_county.xlsx', 'wb') as f:
            f.write(r.content)
        print('Saved to tehama_tax_sale_county.xlsx')
        
        import pandas as pd
        df = pd.read_excel(io.BytesIO(r.content), sheet_name=None)
        for sheet_name, sheet_df in df.items():
            print(f'\nSheet: {sheet_name}, rows={len(sheet_df)}, cols={list(sheet_df.columns)}')
            print(sheet_df.head(5).to_string())
            # Search for our APN
            for col in sheet_df.columns:
                try:
                    hits = sheet_df[sheet_df[col].astype(str).str.replace('-','').str.strip() == APN_CLEAN]
                    if len(hits) > 0:
                        print(f'*** FOUND APN {APN} in column {col}! ***')
                        print(hits.to_string())
                except: pass
except Exception as e:
    print(f'ERROR: {e}')

print()

# ── 3. ParcelQuest Tehama assessor ───────────────────────────────────────────
print('=== PARCELQUEST TEHAMA ===')
# ParcelQuest is the county-endorsed property lookup - try direct APN lookup
pq_urls = [
    f'https://assr.parcelquest.com/impl/TEHASSR',
    f'https://assr.parcelquest.com/impl/TEHASSR?APN={APN}',
    f'https://assr.parcelquest.com/Statewide?apn={APN}&county=Tehama',
    f'https://assr.parcelquest.com/Statewide',
]
for url in pq_urls:
    try:
        rp = s.get(url, timeout=10)
        ct = rp.headers.get('content-type', '')
        print(f'{url} -> {rp.status_code}, len={len(rp.text)}, ct={ct}')
        if rp.status_code == 200 and len(rp.text) > 200:
            print(f'  SAMPLE: {rp.text[:300]}')
    except Exception as e:
        print(f'{url} -> ERROR: {e}')

print()

# ── 4. MPTS common3 Public Inquiry ───────────────────────────────────────────
print('=== MPTS COMMON3 PUBLIC INQUIRY ===')
# This is a different MPTS interface - common3 vs common1
mpts3_base = 'https://common3.mptsweb.com'
paths = [
    '/MegabyteCommonSite/PublicInquiry/Inquiry.aspx?CN=tehama&SITE=Public&DEPT=Asr&PG=Search',
    f'/MegabyteCommonSite/PublicInquiry/Inquiry.aspx?CN=tehama&SITE=Public&DEPT=Asr&PG=Search&APN={APN_CLEAN}',
    f'/mbap/tehama/asr/AsrPrint/{APN_CLEAN}',
]
for path in paths:
    try:
        r3 = s.get(f'{mpts3_base}{path}', timeout=10)
        ct = r3.headers.get('content-type', '')
        print(f'{path} -> {r3.status_code}, len={len(r3.text)}, ct={ct}')
        if r3.status_code == 200:
            soup3 = BeautifulSoup(r3.text, 'html.parser')
            # Get table rows
            for tr in soup3.find_all('tr')[:20]:
                cells = [c.get_text(strip=True) for c in tr.find_all(['td','th'])]
                if cells and any(c.strip() for c in cells):
                    print(f'  ROW: {cells}')
    except Exception as e:
        print(f'{path} -> ERROR: {e}')

print()

# ── 5. tax.tehama.gov - the View/Pay Taxes portal ────────────────────────────
print('=== TAX.TEHAMA.GOV ===')
try:
    rt = s.get('http://tax.tehama.gov', timeout=10, allow_redirects=True)
    print(f'tax.tehama.gov -> {rt.status_code}, url={rt.url}, len={len(rt.text)}')
    soup_t = BeautifulSoup(rt.text, 'html.parser')
    print(f'Title: {soup_t.find("title").get_text() if soup_t.find("title") else "?"}')
    for inp in soup_t.find_all(['input', 'select', 'form'])[:15]:
        print(f'  {inp.name}: id={inp.get("id")} name={inp.get("name")} value={str(inp.get("value",""))[:40]}')
except Exception as e:
    print(f'tax.tehama.gov ERROR: {e}')
