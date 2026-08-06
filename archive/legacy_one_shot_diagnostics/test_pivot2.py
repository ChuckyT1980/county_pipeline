import sys
import os
import pandas as pd
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "tax_pipeline")))
from stage2_http import run_stage2_http
from stage2_recorder_enrich import OwnerVesting, EncumbranceSummary, RecorderEvent, OwnershipVerificationStatus, classify_doc_role, determine_entity_type

def test_pivot2(county, doc_raw):
    def format_doc_number(doc_str, county):
        if not doc_str or pd.isna(doc_str): return None
        doc_str = str(doc_str).strip()
        if county.lower() == "tehama":
            return doc_str.replace('R', '') if isinstance(doc_str, str) else doc_str
        if county.lower() == "shasta":
            if 'R' in doc_str:
                return doc_str.replace('R', '-')
            if '-' not in doc_str and len(doc_str) >= 11:
                return doc_str[:4] + '-' + doc_str[4:]
        return doc_str

    if county.lower() == "tehama":
        from tehama_recorder_api import TehamaRecorderClient
        client = TehamaRecorderClient(delay_between_requests=0.1)
        search_type_name = "DOCSEARCH4S1"
        doc_search_type_name = "DOCSEARCH4S2"
    else:
        from shasta_recorder_api import ShastaRecorderClient
        client = ShastaRecorderClient(delay_between_requests=0.4)
        search_type_name = "DOCSEARCH344S4"
        doc_search_type_name = "DOCSEARCH344S5"

    doc_fmt = format_doc_number(doc_raw, county)
    print(f"\n--- Testing {county.upper()} Pivot 2 for Doc {doc_fmt} ---")
    
    chain = []
    
    client.submit_doc_search(doc_fmt)
    results, total = client.get_results(search_type=doc_search_type_name, page=1)
    if not results:
        print("No results for Pivot 1!")
        return
        
    res = results[0]
    grantee_name = res.grantees[0] if res.grantees else None
    grantor_name = res.grantors[0] if res.grantors else None
    primary_name = grantee_name or grantor_name
    
    print(f"Pivot 1 Owner: {primary_name}")
    nr_type = res.doc_type if res.doc_type else "UNKNOWN"
    nr_date = None
    if res.recording_date:
        parsed_nr = pd.to_datetime(res.recording_date, errors='coerce')
        if not pd.isna(parsed_nr):
            nr_date = parsed_nr.isoformat()
            
    chain.append({
        "event_id": f"{res.doc_number}_0",
        "doc_type": nr_type,
        "doc_number": res.doc_number,
        "grantor": grantor_name,
        "grantee": grantee_name,
        "source": "recorder_pivot1"
    })
    
    print(f"Submitting Pivot 2 Name Search for: {primary_name}")
    client.submit_search(primary_name)
    name_results, _ = client.get_results(search_type=search_type_name, page=1)
    
    for nr_i, nr in enumerate(name_results):
        if nr.doc_number == doc_fmt:
            continue
        nr_type = nr.doc_type if nr.doc_type else "UNKNOWN"
        nr_date = None
        if nr.recording_date:
            parsed_nr = pd.to_datetime(nr.recording_date, errors='coerce')
            if not pd.isna(parsed_nr):
                nr_date = parsed_nr.isoformat()
        chain.append({
            "event_id": f"{nr.doc_number}_{nr_i+1}",
            "doc_type": nr_type,
            "doc_number": nr.doc_number,
            "grantor": nr.grantors[0] if nr.grantors else None,
            "grantee": nr.grantees[0] if nr.grantees else None,
            "source": "recorder_pivot2"
        })
        
        print(f"Pivot 2 Name Search retrieved {len(chain)} events.")
        
    out_file = f"pivot2_output_{county}.json"
    with open(out_file, "w") as f:
        json.dump(chain, f, indent=2)
    print(f"Saved {out_file}")
    client.close()

if __name__ == "__main__":
    # Test Tehama: Miller 1991 (from earlier test) - doc 2018007697
    test_pivot2("tehama", "2018R007697")
    # Test Shasta: SMITH JOHN (from earlier test) - doc 2018R0007697
    test_pivot2("shasta", "2018R0007697")
