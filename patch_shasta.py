import sys
import os

with open('tax_pipeline/stage2_recorder_enrich.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'def run_stage2_shasta_http' not in content:
    from_shasta = '''
from shasta_recorder_api import ShastaRecorderClient

def run_stage2_shasta_http(input_csv, county):
    print(f"Starting HTTP Stage 2 Recorder Enrichment on {input_csv} for {county}...")
    import pandas as pd
    import json
    import os
    import time
    df = pd.read_csv(input_csv)
    checkpoint_file = input_csv.replace('.csv', '_ENRICHED_partial.parquet')
    
    processed_apns = set()
    results_list = []
    
    if os.path.exists(checkpoint_file):
        existing_df = pd.read_parquet(checkpoint_file)
        results_list = existing_df.to_dict("records")
        processed_apns = set(existing_df["parcel_number"].dropna().tolist())
        print(f"Resuming from checkpoint: {len(processed_apns)} already processed.")
        
    # As requested by the user, we use a slower delay of 0.4s for Shasta to avoid rate limiting
    client = ShastaRecorderClient(delay_between_requests=0.4) 
    consecutive_errors = 0
    
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
            results_list.append(row.to_dict())
            processed_apns.add(apn)
            continue
            
        print(f"[{i+1}/{len(df)}] Pivot 1 HTTP: Extracting Vesting for {apn} via Doc {doc_fmt}...")
        
        try:
            client.submit_doc_search(doc_fmt)
            results, total = client.get_results(page=1)
            
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
                client = ShastaRecorderClient(delay_between_requests=0.6)
                consecutive_errors = 0
                
        if vesting.primary_name and not vesting.ownership_verification_status:
            vesting.ownership_verification_status = OwnershipVerificationStatus.MATCHES_ASSESSOR
            
        adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
        for k, v in adjud.items():
            row[k] = v
            
        row["owner_vesting"] = vesting.model_dump_json()
        row["encumbrance_summary"] = encumbrance.model_dump_json()
        row["recorder_chain"] = json.dumps([c.model_dump() for c in chain])
        
        results_list.append(row.to_dict())
        processed_apns.add(apn)
        
        if len(results_list) % 50 == 0:
            pd.DataFrame(results_list).to_parquet(checkpoint_file, index=False)
            print(f"Checkpoint saved: {len(results_list)} records")

    client.close()
    
    out_csv = input_csv.replace('.csv', '_ENRICHED.csv')
    df_out = pd.DataFrame(results_list)
    df_out.to_csv(out_csv, index=False)
    print(f"Saved final to {out_csv}")
'''

    content = content.replace('if county.lower() == "tehama":', from_shasta + '\n    if county.lower() == "tehama":')
    content = content.replace('if county.lower() == "tehama":\n        return run_stage2_tehama_http(input_csv, county)', 'if county.lower() == "tehama":\n        return run_stage2_tehama_http(input_csv, county)\n    if county.lower() == "shasta":\n        return run_stage2_shasta_http(input_csv, county)')
    
    with open('tax_pipeline/stage2_recorder_enrich.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Updated stage2_recorder_enrich.py with Shasta HTTP')
else:
    print('Already updated')
