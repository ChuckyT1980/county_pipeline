import pandas as pd

df = pd.read_csv('tax_pipeline/tehama_MASTER_leads_with_liens.csv')
df['Balance_Val'] = pd.to_numeric(df['live_total_balance'], errors='coerce').fillna(0.0)

# Show the 4 rows with highest balance (our Tier 1 targets)
top = df.nlargest(10, 'Balance_Val')
for i, row in top.iterrows():
    print(f"\nRow {i}: {row['assessee_name']}")
    print(f"  fee_parcel  : {row.get('fee_parcel','?')}")
    print(f"  apn_pdf     : {row.get('apn_pdf','?')}")
    print(f"  address     : {row.get('address','?')}")
    print(f"  situs_pdf   : {row.get('situs_pdf','?')}")
    print(f"  legal_desc  : {row.get('legal_desc','?')}")
    print(f"  asrprint_url: {row.get('asrprint_url','?')}")
    print(f"  asrprint_status: {row.get('asrprint_status','?')}")
    print(f"  net_assessed: {row.get('net_assessed_value','?')}")
    print(f"  balance     : {row['Balance_Val']}")
