from bs4 import BeautifulSoup
import re

with open(r'C:\Users\chuck\Downloads\county_pipeline\kern\govease_captured_55.json', 'r', encoding='utf-8', errors='ignore') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

print("Title:", soup.title.text if soup.title else "No title")

tables = soup.find_all('table')
print(f"Tables count: {len(tables)}")
for i, table in enumerate(tables):
    print(f"\n--- TABLE {i+1} ---")
    rows = table.find_all('tr')
    for row in rows[:10]:
        cols = [c.get_text().strip() for c in row.find_all(['th', 'td'])]
        if cols:
            print(" | ".join(cols))

links = soup.find_all('a', href=True)
print(f"\nLinks count: {len(links)}")
for l in links:
    href = l['href']
    if any(k in href.lower() or k in l.text.lower() for k in ['auction', 'parcel', 'property', 'browse', 'list', 'detail']):
        print(f"  Link text: '{l.text.strip()}' -> {href}")
