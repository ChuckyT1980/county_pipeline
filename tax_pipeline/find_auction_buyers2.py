"""Test different county name searches to find auction deed recordings."""
import sys, json, time, re
sys.path.insert(0, ".")

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with open("tyler_session_cookies.json") as f:
    cookies = json.load(f)

p = sync_playwright().__enter__()
b = p.chromium.launch(headless=True)
ctx = b.new_context(viewport={"width": 1280, "height": 900})
ctx.add_cookies(cookies)
page = ctx.new_page()
page.set_default_timeout(15000)

def search_by_name(name):
    page.goto("https://recorder.buttecounty.net/web/search/DOCSEARCH481S1", wait_until="networkidle", timeout=20000)
    time.sleep(2)
    page.fill("#field_BothNamesID", name)
    page.keyboard.press("Escape")
    time.sleep(0.5)
    page.click("#searchButton")
    time.sleep(5)
    return page.content()

html = search_by_name("BUTTE COUNTY")
soup = BeautifulSoup(html, "html.parser")
rows = soup.select("li.ss-search-row")
print(f"Search 'BUTTE COUNTY': {len(rows)} results")
for row in rows[:10]:
    h1 = row.find("h1")
    if h1:
        print(f"  {h1.get_text(strip=True)[:120]}")

html = search_by_name("COUNTY OF BUTTE")
soup = BeautifulSoup(html, "html.parser")
rows = soup.select("li.ss-search-row")
print(f"\nSearch 'COUNTY OF BUTTE': {len(rows)} results")

html = search_by_name("TAX COLLECTOR")
soup = BeautifulSoup(html, "html.parser")
rows = soup.select("li.ss-search-row")
print(f"\nSearch 'TAX COLLECTOR': {len(rows)} results")
for row in rows[:5]:
    h1 = row.find("h1")
    if h1:
        print(f"  {h1.get_text(strip=True)[:120]}")

html = search_by_name("RESCISSION")
soup = BeautifulSoup(html, "html.parser")
rows = soup.select("li.ss-search-row")
print(f"\nSearch 'RESCISSION': {len(rows)} results")
for row in rows[:20]:
    h1 = row.find("h1")
    if not h1: continue
    h1_text = h1.get_text(strip=True)
    doc_match = re.search(r"(\d{4}-\d{7})", h1_text)
    doc_num = doc_match.group(1) if doc_match else "?"
    doc_type = h1_text[len(doc_num):].strip() if doc_match else h1_text
    
    grantor_vals = []
    grantee_vals = []
    rec_date = ""
    for col in row.find_all("div", class_="searchResultThreeColumn"):
        header = col.find("li")
        if not header: continue
        h = header.get_text(strip=True).upper()
        vals = [b.get_text(strip=True) for b in col.find_all("b") if b.get_text(strip=True)]
        if "GRANTOR" in h: grantor_vals = vals
        elif "GRANTEE" in h: grantee_vals = vals
        elif "RECORDING" in h and vals: rec_date = vals[0]
    
    grantee = "; ".join(grantee_vals)[:60]
    grantor = "; ".join(grantor_vals)[:60]
    print(f"  {doc_num} {rec_date[:20] if rec_date else '':15s} {grantor:30s} -> {grantee:30s}")

b.close()
p.stop()
