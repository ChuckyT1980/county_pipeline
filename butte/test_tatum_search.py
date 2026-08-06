import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tyler_recorder_client import TylerRecorderClient, BUTTE

client = TylerRecorderClient(BUTTE)
try:
    print("Searching Tyler Recorder for 'TATUM FRANK'...")
    client.submit_name_search("TATUM FRANK")
    results, total = client.get_results(search_type="name")
    print(f"Total results: {total}")
    for idx, r in enumerate(results[:10]):
        print(f"Doc {idx}: ID={r.doc_id} Number={r.doc_number} Type={r.doc_type} Date={r.recording_date}")
        print(f"  Grantors: {r.grantors}")
        print(f"  Grantees: {r.grantees}")
finally:
    client.close()
