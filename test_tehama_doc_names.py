"""Live test: Tehama S2 doc search with r_to_strip transform applied."""
import sqlite3, sys
sys.path.insert(0, r"C:\Users\chuck\Downloads\county_pipeline")
from tyler_recorder_client import TylerRecorderClient, CountyConfig, apply_doc_transform

TEHAMA_STRIP = CountyConfig(
    county="tehama",
    base_url="https://recordsearch.tehama.gov",
    name_search_id="DOCSEARCH4S1",
    doc_search_id="DOCSEARCH4S2",
    ajax_headers_required=True,
    doc_number_transform="r_to_strip",
)

con = sqlite3.connect(r"C:\Users\chuck\Downloads\county_pipeline\data\counties\tehama\state.sqlite")
docs = con.execute(
    "SELECT apn, current_doc_number FROM parcels "
    "WHERE current_doc_number LIKE '%R%' LIMIT 8"
).fetchall()

client = TylerRecorderClient(TEHAMA_STRIP)
try:
    for apn, doc in docs:
        stripped = apply_doc_transform(doc, "r_to_strip")
        print(f"\n--- {apn} doc={doc} -> {stripped}")
        try:
            client.submit_doc_search(stripped)
            results, total = client.get_results(search_type="doc")
            print(f"  total={total}")
            for r in results[:3]:
                print(f"  {r.doc_number} | {r.doc_type} | {r.recording_date}")
                print(f"    grantors:  {r.grantors}")
                print(f"    grantees:  {r.grantees}")
        except Exception as e:
            print(f"  ERROR: {e}")
finally:
    client.close()
