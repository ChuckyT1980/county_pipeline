import requests
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

# Accept disclaimer
s.post("https://recordsearch.tehama.gov/web/disclaimer/accept", data={"action":"accept"})

# Search
r = s.get("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1?lastName=SOTO&firstName=JOSE")
soup = BeautifulSoup(r.text, 'html.parser')

print("Result items:")
for li in soup.find_all("li", class_="ui-li-static")[:3]:
    print("--- ITEM ---")
    for div in li.find_all("div"):
        print(div.get("class"), div.text.strip())
