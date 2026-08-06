"""Check Butte AsrPrint page HTML to find owner name selector."""
import requests
from bs4 import BeautifulSoup

asmt_raw = "002271003000"
asr_url = f"https://common2.mptsweb.com/mbap/butte/asr/AsrPrint/{asmt_raw}"

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})
resp = s.get(asr_url, timeout=15)
print(f"Status: {resp.status_code}")
print(f"URL: {resp.url}")

soup = BeautifulSoup(resp.text, "html.parser")

# Dump all table rows
print("\n=== Table rows (tr > td/th) ===")
for tr in soup.find_all("tr"):
    cells = tr.find_all(["td", "th"])
    if len(cells) >= 2:
        label = cells[0].get_text(strip=True)
        value = cells[1].get_text(strip=True)
        if label:
            print(f"  '{label}' -> '{value[:80]}'")

# Also check for any text containing "owner" or "name"
print("\n=== Text containing 'owner' or 'name' (case-insensitive) ===")
body_text = soup.get_text("\n")
for ln in body_text.split("\n"):
    ln = ln.strip()
    if ln and ("owner" in ln.lower() or "name" in ln.lower() or "assessee" in ln.lower()):
        print(f"  '{ln[:100]}'")
