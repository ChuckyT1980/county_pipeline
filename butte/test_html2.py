from butte_tax_api import ButteTaxClient

client = ButteTaxClient()
client._init_session()
resp = client.client.get(f"/MBC/butte/tax/main/027290021000/{client.roll_year}/0000")
with open("temp_027290021.html", "w", encoding="utf-8") as f:
    f.write(resp.text)
print("Saved HTML")
