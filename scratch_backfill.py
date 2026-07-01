import pandas as pd
import sys
sys.path.append('tax_pipeline')
from stage4_owner_enrich import fetch_asr_print
import time

file_path = 'tax_pipeline/tehama_MASTER_leads_with_liens.csv'
df = pd.read_csv(file_path)

missing = df["address"].isna().sum()
print(f'Found {missing} rows missing address.')
count = 0
for idx, row in df.iterrows():
    if pd.isna(row['address']):
        apn = str(row.get('fee_parcel'))
        if apn == 'nan' or apn == 'None':
            apn = str(row.get('apn_pdf', ''))
        
        apn = apn.replace('.0', '').strip()
        if apn:
            print(f'Fetching for {apn}...')
            asr_data = fetch_asr_print(apn)
            situs = asr_data.get('situs_full')
            if situs:
                df.at[idx, 'address'] = situs
                count += 1
            time.sleep(0.5)

df.to_csv(file_path, index=False)
print(f'Backfilled {count} addresses!')
