import pandas as pd
import json

df = pd.read_parquet('shasta/shasta_15_percent_sample_VERIFIED_ENRICHED_partial.parquet')
for _, row in df.iterrows():
    v = json.loads(row.get('owner_vesting', '{}'))
    chain = json.loads(row.get('chain_of_title', '[]'))
    if v.get('primary_name') and v.get('vesting_doc_type') and len(chain) > 0:
        print('=== STAGE 1 DATA (Tax Portal) ===')
        print(f'Parcel Number: {row.get("parcel_number")}')
        print(f'Total Due: {row.get("v_total_due")}')
        print(f'Total Paid: {row.get("v_total_paid")}')
        print(f'Total Balance: {row.get("v_total_balance")}')
        print(f'Delinquent Flag: {row.get("v_delinquent")}')
        print(f'Base Doc Number: {row.get("v_document_number")}')
        
        print('\n=== STAGE 2 DATA (Recorder Portal) ===')
        print(f'Owner Name: {v.get("primary_name")}')
        print(f'Entity Type: {v.get("entity_type")}')
        print(f'Doc Type: {v.get("vesting_doc_type")}')
        print(f'Recording Date: {v.get("acquisition_date")}')
        
        chain = json.loads(row.get('chain_of_title', '[]'))
        print(f'\n=== CHAIN OF TITLE (Encumbrances) ===')
        if not chain:
            print('- None found')
        for evt in chain:
            print(f"- {evt.get('doc_type')} ({evt.get('role')}) - {evt.get('recorded_date')}")
        break
