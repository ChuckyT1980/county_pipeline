import time, httpx
from bs4 import BeautifulSoup

client = httpx.Client(base_url='https://recorder.buttecounty.net', follow_redirects=True, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
client.get('/web/user/disclaimer'); time.sleep(0.3)
client.post('/web/user/disclaimer'); time.sleep(0.3)
client.get('/web/search/DOCSEARCH481S2'); time.sleep(0.3)
r = client.post('/web/searchPost/DOCSEARCH481S2',
    data={'field_DocumentNumberID': '2024-0030607', 'field_BookPageID_DOT_Volume': '', 'field_BookPageID_DOT_Page': ''},
    headers={'ajaxrequest': 'true', 'x-requested-with': 'XMLHttpRequest'})

soup = BeautifulSoup(r.text, 'html.parser')
seen = set()
count = 0
for el in soup.find_all(['h1','h2','h3','p','li','span','div']):
    t = el.get_text(strip=True)
    if t and 5 < len(t) < 200 and t not in seen:
        seen.add(t)
        print(repr(t))
        count += 1
        if count >= 40:
            break
client.close()
