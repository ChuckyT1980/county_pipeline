import pandas as pd

df = pd.read_csv('tax_pipeline/tehama_MASTER_leads_with_liens.csv')

# Replicate dashboard scoring to find Tier 1
df['Balance_Val'] = pd.to_numeric(df['live_total_balance'], errors='coerce').fillna(0.0)

print(f"Total rows: {len(df)}")
print("\n--- All address fields for every row ---")
for i, row in df.iterrows():
    nav = str(row.get('net_assessed_value', ''))
    score_proxy = df['Balance_Val'].iloc[i]
    print(f"\nRow {i}: assessee={row.get('assessee_name','?')}")
    print(f"  address     : {repr(row.get('address', ''))}")
    print(f"  situs_pdf   : {repr(row.get('situs_pdf', ''))}")
    print(f"  legal_desc  : {repr(row.get('legal_desc', ''))}")
    print(f"  net_assessed: {nav}")
    print(f"  balance     : {score_proxy}")
