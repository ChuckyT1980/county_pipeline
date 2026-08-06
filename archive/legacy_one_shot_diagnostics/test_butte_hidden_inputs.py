import httpx, time
from bs4 import BeautifulSoup

client = httpx.Client(base_url='https://recorder.buttecounty.net', follow_redirects=True,
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
client.get('/web/user/disclaimer'); time.sleep(0.3)
client.post('/web/user/disclaimer'); time.sleep(0.3)
r = client.get('/web/search/DOCSEARCH481S2'); time.sleep(0.3)

soup = BeautifulSoup(r.text, 'html.parser')

# All hidden inputs anywhere on page (not just inside form tags)
hidden = soup.find_all('input', {'type': 'hidden'})
print(f"Hidden inputs anywhere on page: {len(hidden)}")
for h in hidden:
    name = h.get('name', '')
    val = str(h.get('value', ''))[:80]
    print(f"  name={name!r}  value={val!r}")

# Meta tags with token/csrf in name or content
print()
metas = [m for m in soup.find_all('meta') if any(k in str(m).lower() for k in ['csrf', 'token', 'state'])]
print(f"Meta token/csrf/state tags: {len(metas)}")
for m in metas:
    print(f"  {m}")

client.close()
