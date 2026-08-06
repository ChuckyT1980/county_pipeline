"""Use Tyler recorder session to find all auction buyers from June 2026."""
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

# Search for county as grantor (post-auction tax deeds)
html = search_by_name("BUTTE COUNTY TAX COLLECTOR")
soup = BeautifulSoup(html, "html.parser")

def parse_events(soup):
    events = []
    for row in soup.select("li.ss-search-row"):
        h1 = row.find("h1")
        if not h1:
            continue
        h1_text = h1.get_text(strip=True)
        doc_match = re.search(r"(\d{4}-\d{7})", h1_text)
        if not doc_match:
            continue
        doc_num = doc_match.group(1)
        doc_type = h1_text.split(doc_num)[-1].strip() if doc_num in h1_text else ""

        grantor_vals = []
        grantee_vals = []
        rec_date = ""
        for col in row.find_all("div", class_="searchResultThreeColumn"):
            header = col.find("li")
            if not header:
                continue
            h = header.get_text(strip=True).upper()
            vals = [b.get_text(strip=True) for b in col.find_all("b") if b.get_text(strip=True)]
            if "GRANTOR" in h:
                grantor_vals = vals
            elif "GRANTEE" in h:
                grantee_vals = vals
            elif "RECORDING" in h and vals:
                rec_date = vals[0]
        events.append({
            "doc": doc_num,
            "type": doc_type,
            "date": rec_date,
            "grantee": "; ".join(grantee_vals),
        })
    return events

events = parse_events(soup)
print(f"BUTTE COUNTY TAX COLLECTOR: {len(events)} events")

# Filter for June/July 2026 (post-auction)
post_auction = [e for e in events if any(m in e["date"] for m in ["06/", "07/"])]
print(f"Post-auction (June/July 2026): {len(post_auction)}")

# Group by grantee (buyer)
from collections import Counter
buyers = Counter()
for e in post_auction:
    if e["grantee"] and "BUTTE COUNTY" not in e["grantee"].upper():
        buyers[e["grantee"]] += 1

print(f"\nUnique buyers: {len(buyers)}")
print(f"\n{'BUYER':<50s} {'DEEDS':>5s}")
print("-" * 55)
for name, cnt in buyers.most_common(30):
    print(f"  {name:<48s} {cnt:3d}")

# Also check BUTTE COUNTY TREASURER
html2 = search_by_name("BUTTE COUNTY TREASURER")
events2 = parse_events(BeautifulSoup(html2, "html.parser"))
post2 = [e for e in events2 if any(m in e["date"] for m in ["06/", "07/"])]
buyers2 = Counter()
for e in post2:
    if e["grantee"] and "BUTTE COUNTY" not in e["grantee"].upper():
        buyers2[e["grantee"]] += 1
print(f"\nBUTTE COUNTY TREASURER post-auction: {len(events2)} events, {len(buyers2)} unique buyers")
for name, cnt in buyers2.most_common(20):
    print(f"  {name:<48s} {cnt:3d}")

print("\nDone.")
b.close()
p.stop()
