from butte_tax_api import ButteTaxClient
client = ButteTaxClient()
res = client.get_detail("022-210-078-000")
print("--- 022-210-078-000 ---")
if res:
    print(f"Total Defaulted: {res.total_defaulted_balance}")
    print("Defaults:")
    for t in res.defaulted_taxes:
        print(f"  - {vars(t)}")
else:
    print("No results found.")
