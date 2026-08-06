import requests, re, sys
from bs4 import BeautifulSoup

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

asmt = "085040018000"  # known-good APN from verified data
url = f"https://common1.mptsweb.com/mbap/tehama/asr/AsrPrint/{asmt}"
r = s.get(url, timeout=15)
print("status:", r.status_code, "len:", len(r.text))
soup = BeautifulSoup(r.text, "html.parser")
rows = []
for tr in soup.find_all("tr"):
    cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
    if cells:
        rows.append(cells)
for row in rows:
    print(row)
