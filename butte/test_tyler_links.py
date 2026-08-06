import httpx
from bs4 import BeautifulSoup

resp = httpx.get("https://recorder.buttecounty.net/web/")
soup = BeautifulSoup(resp.text, "html.parser")
for a in soup.find_all("a"):
    if "search" in (a.get("href") or "").lower():
        print(a.get_text(strip=True), a.get("href"))
