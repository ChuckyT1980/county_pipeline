import httpx, time, re
from bs4 import BeautifulSoup

test_parcels = ['002-292-001-000', '003-310-021-000', '003-470-002-000']

client = httpx.Client(
    base_url='https://common2.mptsweb.com',
    follow_redirects=True,
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'}
)
client.get('/mbc/butte/tax/search')
time.sleep(0.5)

def to_undashed(p): return re.sub(r'\D', '', p)

for parcel in test_parcels:
    parcel12 = to_undashed(parcel)
    r = client.get(f'/MBC/butte/tax/main/{parcel12}/2026/0000')
    time.sleep(0.5)
    soup = BeautifulSoup(r.text, 'html.parser')

    # Assessment fields via dl/dt/dd
    fields = {}
    for dl in soup.find_all('dl'):
        for dt, dd in zip(dl.find_all('dt'), dl.find_all('dd')):
            label = dt.get_text(strip=True)
            if label:
                fields[label] = dd.get_text(' ', strip=True)

    # Defaulted taxes via div.col-sm-3 rows
    defaults = []
    for row_div in soup.find_all('div'):
        cells = row_div.find_all('div', class_='col-sm-3', recursive=False)
        if len(cells) != 4:
            continue
        labels = [c.find('strong').get_text(strip=True) if c.find('strong') else '' for c in cells]
        if 'Default Number' not in labels:
            continue
        vals = []
        for c in cells:
            inner = c.find_all('div', recursive=False)
            vals.append(inner[1].get_text(strip=True) if len(inner) >= 2 else '')
        row_data = dict(zip(labels, vals))
        defaults.append(row_data)

    print(f"--- {parcel} ---")
    print(f"  Doc#: {fields.get('Document Number', 'MISSING')}")
    print(f"  Roll: {fields.get('Roll Category', 'MISSING')}")
    print(f"  Addr: {fields.get('Address', 'MISSING')}")
    print(f"  Defaults ({len(defaults)}): {defaults}")
    print()

client.close()
