import sys
sys.path.insert(0, r"C:\Users\chuck\Downloads\county_pipeline")
from tyler_recorder_client import TylerRecorderClient, FRESNO

client = TylerRecorderClient(FRESNO)
try:
    client.submit_apn_search("09010115")
    results, total = client.get_results(search_type="apn")
    print("total:", total)
    for r in results:
        print(r.doc_number, "|", r.recording_date, "|", r.grantors, "|", r.grantees)
finally:
    client.close()
