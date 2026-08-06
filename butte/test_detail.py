from butte_tax_api import ButteTaxClient
client = ButteTaxClient()
res = client.get_detail("027-290-021-000")
if res:
    print(res)
else:
    print("None")
