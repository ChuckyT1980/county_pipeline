"""Print the full raw error page from searchPost to find exception type/message."""
import httpx, time
from bs4 import BeautifulSoup

client = httpx.Client(base_url='https://recorder.buttecounty.net', follow_redirects=True,
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'})

client.get('/web/user/disclaimer'); time.sleep(0.3)
client.post('/web/user/disclaimer'); time.sleep(0.3)
client.get('/web/search/DOCSEARCH481S2'); time.sleep(0.3)

r = client.post(
    '/web/searchPost/DOCSEARCH481S2',
    data={'field_DocumentNumberID': '2024-0030607', 'field_BookPageID_DOT_Volume': '', 'field_BookPageID_DOT_Page': ''},
    headers={'ajaxrequest': 'true', 'x-requested-with': 'XMLHttpRequest'},
)

print(f"Status: {r.status_code}  len={len(r.text)}")
print()

# Print full raw body — all 13k — to find actual exception message
print("=== FULL RAW BODY ===")
print(r.text)

client.close()
