import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'butte')))

from butte_tax_api import ButteTaxClient

client = ButteTaxClient()
try:
    print("Fetching tax detail for 027-290-021-000...")
    res = client.get_detail("027-290-021-000")
    print(f"RAW RESULT: {res}")
    if res:
        print(f"document_number_raw = '{res.document_number_raw}'")
finally:
    client.close()
