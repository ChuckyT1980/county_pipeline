import requests
from bs4 import BeautifulSoup

apn = "002271003000"
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})

url = f"https://common1.mptsweb.com/mbap/butte/asr/AsrPrint/{apn}"
r = s.get(url, timeout=15)
print(f"Status: {r.status_code}, Length: {len(r.text)}")

soup = BeautifulSoup(r.text, "html.parser")
rows = soup.find_all("tr")
data = {}
for row in rows:
    cells = row.find_all(["td", "th"])
    if len(cells) >= 2:
        label = cells[0].get_text(strip=True)
        value = cells[1].get_text(strip=True)
        data[label] = value
        print(f"  {label}: {value[:80]}")

print(f"\nAssessee Name: {data.get('Assessee Name', 'NOT FOUND')}")
print(f"Owner Name: {data.get('Owner Name', 'NOT FOUND')}")
print(f"Document Number: {data.get('Current Document Number', 'NOT FOUND')}")
print(f"Property Type: {data.get('Property Type', 'NOT FOUND')}")
print(f"Net Assessed Value: {data.get('Net Assessed Value', 'NOT FOUND')}")
