import pandas as pd
import json
import os

def rollback_file(county, path):
    if not os.path.exists(path):
        return 0
    df = pd.read_parquet(path)
    
    # Find the first row where internet dropped
    # It drops when v_document_number is NOT null, but owner_vesting json has no ownership_verification_status
    safe_limit = len(df)
    for i, row in df.iterrows():
        if pd.notna(row.get('v_document_number')):
            try:
                vesting = json.loads(row.get('owner_vesting', '{}'))
                status = vesting.get('ownership_verification_status')
                if not status:
                    # Internet dropped here
                    safe_limit = i
                    break
            except:
                safe_limit = i
                break
                
    if safe_limit < len(df):
        print(f"{county}: Rolling back from {len(df)} to {safe_limit}")
        df_safe = df.iloc[:safe_limit]
        df_safe.to_parquet(path)
    else:
        print(f"{county}: No rollback needed, size {len(df)}")
    return safe_limit

tehama_path = 'tehama/tehama_15_percent_sample_VERIFIED_ENRICHED_partial.parquet'
shasta_path = 'shasta/shasta_15_percent_sample_VERIFIED_ENRICHED_partial.parquet'

t_size = rollback_file('Tehama', tehama_path)
s_size = rollback_file('Shasta', shasta_path)

if os.path.exists('tehama/tehama_15_percent_sample_ENRICHED.csv'):
    os.remove('tehama/tehama_15_percent_sample_ENRICHED.csv')
if os.path.exists('shasta/shasta_15_percent_sample_ENRICHED.csv'):
    os.remove('shasta/shasta_15_percent_sample_ENRICHED.csv')
