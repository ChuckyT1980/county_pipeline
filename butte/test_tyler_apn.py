import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), '..')))

from tyler_recorder_client import TylerRecorderClient, BUTTE

client = TylerRecorderClient(BUTTE)
try:
    print("Testing 027-290-021-000...")
    docs1 = client.get_chain_for_apn("027-290-021-000")
    print(f"Found: {len(docs1)}")
    
    print("Testing 027-290-021...")
    docs2 = client.get_chain_for_apn("027-290-021")
    print(f"Found: {len(docs2)}")
    
    print("Testing 027290021000...")
    docs3 = client.get_chain_for_apn("027290021000")
    print(f"Found: {len(docs3)}")
    
    print("Testing 027290021...")
    docs4 = client.get_chain_for_apn("027290021")
    print(f"Found: {len(docs4)}")
    
    for idx, d in enumerate(docs2):
        print(f"Doc {idx}: {d}")
except Exception as e:
    print("Error:", e)
finally:
    client.close()
