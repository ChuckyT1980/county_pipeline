import pandas as pd
import json

df = pd.read_parquet('shasta/shasta_15_percent_sample_VERIFIED_ENRICHED_partial.parquet')
found = False
for _, row in df.iterrows():
    if True:
        chain = json.loads(row.get('chain_of_title', '[]'))
        if len(chain) > 0:
            print(f'Found APN: {row["parcel_number"]}')
            print('Chain:')
            for evt in chain:
                print(f"  - {evt.get('doc_type')} ({evt.get('role')})")
            
            # Find a truly distressed one (has DEBT or LIEN or DEFAULT)
            roles = [e.get('role') for e in chain]
            if 'DEBT' in roles or 'LIEN' in roles or 'DEFAULT' in roles:
                test_df = pd.DataFrame([row])
                test_df.to_csv('shasta/shasta_test_stage3.csv', index=False)
                print('Saved to shasta/shasta_test_stage3.csv')
                found = True
                break
if not found:
    print('No delinquent rows with chain of title found in the partial parquet yet.')
