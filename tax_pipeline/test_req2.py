import requests
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
r_search = s.get("https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1?lastName=SOTO&firstName=JOSE")

soup = BeautifulSoup(r_search.text, 'html.parser')
for li in soup.find_all("li"):
    print(li.text.strip()[:100])
