import pandas as pd
import re

df = pd.read_csv('shasta/shasta_15_percent_sample_VERIFIED.csv', low_memory=False)

def parse_bal(s):
    try: return float(re.sub(r'[^\d.]', '', str(s)))
    except: return 0.0

df['bal_num'] = df['v_total_balance'].apply(parse_bal)
df_delinq = df[df['v_delinquent'] == True]
df_sorted = df_delinq.sort_values('bal_num', ascending=False)

if not df_sorted.empty:
    top = df_sorted.iloc[0:1].copy()
    top.drop(columns=['bal_num'], inplace=True)
    top.to_csv('shasta/shasta_real_distress.csv', index=False)
    print(f"Found APN {top.iloc[0]['parcel_number']} with balance {top.iloc[0]['v_total_balance']}")
else:
    print('No delinquent properties found.')
