import requests
from bs4 import BeautifulSoup
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0"
r = s.get("https://common1.mptsweb.com/mbap/tehama/asr/AsrPrint/085040018000", timeout=15)
soup = BeautifulSoup(r.text, "html.parser")
for h in soup.find_all(["h1","h2","h3","h4","b","strong"]):
    t = h.get_text(strip=True)
    if t and len(t) < 80:
        print(h.name, "->", t)
print("--- all table headers ---")
for tr in soup.find_all("tr"):
    ths = tr.find_all("th")
    if ths:
        print([t.get_text(strip=True) for t in ths])
