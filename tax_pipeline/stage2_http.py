import pandas as pd
import json
import os
import time

from stage2_recorder_enrich import deterministic_adjudicate
from stage2_recorder_enrich import OwnerVesting, EncumbranceSummary, RecorderEvent, OwnershipVerificationStatus, classify_doc_role, determine_entity_type
from integrity_gate import IntegrityGate

def run_stage2_http(input_csv, county):
    print(f"Starting HTTP Stage 2 Recorder Enrichment (with Pivot 2) on {input_csv} for {county}...")
    
    # We must import the correct client and format_doc_number logic
    # We will just redefine format_doc_number here for safety
    def format_doc_number(doc_str, county="shasta"):
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
        import sys
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from tehama_recorder_api import TehamaRecorderClient
        client = TehamaRecorderClient(delay_between_requests=0.4)
        search_type_name = "DOCSEARCH4S1"
        doc_search_type_name = "DOCSEARCH4S2"
    else:
        import sys
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from shasta_recorder_api import ShastaRecorderClient
        client = ShastaRecorderClient(delay_between_requests=0.8)
        search_type_name = "DOCSEARCH344S4"
        doc_search_type_name = "DOCSEARCH344S5"
        
    df = pd.read_csv(input_csv)
    checkpoint_file = input_csv.replace('.csv', '_ENRICHED_partial.parquet')
    
    processed_apns = set()
    results_list = []
    
    if os.path.exists(checkpoint_file):
        existing_df = pd.read_parquet(checkpoint_file)
        results_list = existing_df.to_dict("records")
        processed_apns = set(existing_df["parcel_number"].dropna().tolist())
        print(f"Resuming from checkpoint: {len(processed_apns)} already processed.")
        
    consecutive_errors = 0
    gate = IntegrityGate(
        check_every=50, 
        input_doc_field="v_document_number",
        county=county.lower(),
        history_file=f"{county.lower()}_integrity_history.jsonl"
    )
    
    for i, row in df.iterrows():
        apn = row.get("parcel_number")
        if pd.isna(apn) or apn in processed_apns:
            continue
            
        doc_raw = row.get("v_document_number")
        doc_fmt = format_doc_number(doc_raw, county)
        
        vesting = OwnerVesting()
        encumbrance = EncumbranceSummary()
        chain = []
        
        if not doc_fmt:
            vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
            adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
            row["owner_vesting"] = vesting.model_dump_json()
            row["encumbrance_summary"] = encumbrance.model_dump_json()
            row["recorder_chain"] = json.dumps([])
            for k, v in adjud.items():
                row[k] = v
            result_dict = row.to_dict()
            results_list.append(result_dict)
            processed_apns.add(apn)
            
            gate.record(result_dict)
            if gate.should_check():
                ok, report = gate.check()
                if not ok:
                    print(report)
                    raise SystemExit("Integrity gate failed")
                else:
                    print(f"[integrity_gate] OK at record {len(results_list)} — {report}")
            
            continue
            
        print(f"[{i+1}/{len(df)}] Pivot 1 HTTP: Extracting Vesting for {apn} via Doc {doc_fmt}...")
        
        try:
            client.submit_doc_search(doc_fmt)
            results, total = client.get_results(search_type=doc_search_type_name, page=1)
            
            if results:
                primary_name = None
                for res in results:
                    grantee_name = res.grantees[0] if res.grantees else None
                    grantor_name = res.grantors[0] if res.grantors else None
                    primary_name = grantee_name or grantor_name
                    
                    if primary_name:
                        vesting.primary_name = primary_name
                        vesting.entity_type = determine_entity_type(primary_name)
                        vesting.acquisition_doc = doc_fmt
                        vesting.verified_current_owner_name = primary_name
                        
                        doc_type_str = res.doc_type if res.doc_type else "UNKNOWN"
                        if doc_type_str and doc_type_str != "UNKNOWN":
                            vesting.vesting_doc_type = doc_type_str
                            
                        if res.recording_date:
                            parsed = pd.to_datetime(res.recording_date, errors='coerce')
                            if not pd.isna(parsed):
                                vesting.acquisition_date = parsed.isoformat()
                                
                        doc_type_str = vesting.vesting_doc_type or "UNKNOWN"
                        chain.append(RecorderEvent(
                            event_id=doc_fmt,
                            doc_type=doc_type_str,
                            role=classify_doc_role(doc_type_str),
                            recorded_date=pd.to_datetime(vesting.acquisition_date).isoformat() if vesting.acquisition_date else None,
                            doc_number=doc_fmt,
                            grantor=grantor_name,
                            grantee=grantee_name,
                            source="recorder"
                        ))
                        vesting.source = "recorder"
                        vesting.confidence = 0.9
                        if not row.get("owner_name") or pd.isna(row.get("owner_name")):
                            row["owner_name"] = primary_name
                            
                        # --- PIVOT 2: NAME SEARCH ---
                        print(f"          Pivot 2 HTTP: Extracting Chain for {primary_name}...")
                        try:
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
                                chain.append(RecorderEvent(
                                    event_id=f"{nr.doc_number}_{nr_i}",
                                    doc_type=nr_type,
                                    role=classify_doc_role(nr_type),
                                    recorded_date=nr_date,
                                    doc_number=nr.doc_number,
                                    grantor=nr.grantors[0] if nr.grantors else None,
                                    grantee=nr.grantees[0] if nr.grantees else None,
                                    source="recorder"
                                ))
                        except Exception as e:
                            print(f"          Pivot 2 HTTP Error: {e}")
                        break
            else:
                vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
                
            consecutive_errors = 0
                
        except Exception as e:
            print(f"  Error fetching HTTP for {doc_fmt}: {e}")
            vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
            row["error"] = str(e)
            consecutive_errors += 1
            if consecutive_errors > 5:
                print("Too many consecutive HTTP errors. Re-initializing session...")
                client.close()
                time.sleep(2)
                if county.lower() == "tehama":
                    client = TehamaRecorderClient(delay_between_requests=0.5)
                else:
                    client = ShastaRecorderClient(delay_between_requests=1.0)
                consecutive_errors = 0
                
        if vesting.primary_name and not vesting.ownership_verification_status:
            vesting.ownership_verification_status = OwnershipVerificationStatus.MATCHES_ASSESSOR
            
        adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
        for k, v in adjud.items():
            row[k] = v
            
        row["owner_vesting"] = vesting.model_dump_json()
        row["encumbrance_summary"] = encumbrance.model_dump_json()
        row["recorder_chain"] = json.dumps([c.model_dump(mode="json") for c in chain])
        
        result_dict = row.to_dict()
        results_list.append(result_dict)
        processed_apns.add(apn)
        
        gate.record(result_dict)
        if gate.should_check():
            ok, report = gate.check()
            if not ok:
                print(report)
                raise SystemExit(
                    "Integrity gate failed — halting pipeline. "
                    "Fix the bug before resuming, don't let this keep writing."
                )
            else:
                print(f"[integrity_gate] OK at record {len(results_list)} — {report}")
        
        if len(results_list) % 50 == 0:
            pd.DataFrame(results_list).to_parquet(checkpoint_file, index=False)
            print(f"Checkpoint saved: {len(results_list)} records")

    client.close()
    
    out_csv = input_csv.replace('.csv', '_ENRICHED.csv')
    df_out = pd.DataFrame(results_list)
    df_out.to_csv(out_csv, index=False)
    print(f"Saved final to {out_csv}")
