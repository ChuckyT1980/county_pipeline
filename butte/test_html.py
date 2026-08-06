from butte_tax_api import ButteTaxClient
from bs4 import BeautifulSoup

client = ButteTaxClient()
client._init_session()
resp = client.client.get(f"/MBC/butte/tax/main/027290021000/{client.roll_year}/0000")
soup = BeautifulSoup(resp.text, "html.parser")
fields = {}
for dl in soup.find_all("dl"):
    dts = dl.find_all("dt")
    dds = dl.find_all("dd")
    for dt, dd in zip(dts, dds):
        label = dt.get_text(strip=True)
        link = dd.find("a")
        if link:
            val = link.get_text(strip=True)
        else:
            val = dd.get_text(" ", strip=True)
        fields[label] = val

print("--- 027-290-021-000 FIELDS ---")
for k, v in fields.items():
    print(f"{k}: {v}")
