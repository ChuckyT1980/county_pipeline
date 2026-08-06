import pandas as pd

df = pd.read_csv(r'C:\Users\chuck\Downloads\county_pipeline\butte\butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv', dtype=str)

df['priority_score'] = pd.to_numeric(df['priority_score'], errors='coerce')
print('=== TOP 10 BY PRIORITY SCORE ===')
top = df.nlargest(10, 'priority_score')
for _, r in top.iterrows():
    name = r.get('verified_current_owner_name', 'N/A') or 'N/A'
    addr = r.get('situs_address', 'N/A') or 'N/A'
    bal = r.get('v_total_balance', 'N/A')
    score = r.get('priority_score', 'N/A')
    print(f'  Score {score}: {name} | {addr} | Bal: {bal}')

print()
print('=== BALANCE STATS ===')
df['bal_num'] = df['v_total_balance'].str.replace(r'[\$,)]', '', regex=True).astype(float)
print(f'  Total balance: ${df["bal_num"].sum():,.0f}')
print(f'  Avg balance: ${df["bal_num"].mean():,.0f}')
print(f'  Median balance: ${df["bal_num"].median():,.0f}')
print(f'  Max: ${df["bal_num"].max():,.0f}')

print()
print('=== PORTFOLIO OWNERS (2+ parcels) ===')
owner_counts = df['verified_current_owner_name'].value_counts()
multi = owner_counts[owner_counts > 1]
print(f'Owners with 2+ parcels: {len(multi)}')
for name, count in multi.items():
    subset = df[df['verified_current_owner_name'] == name]
    apns = subset['apn'].tolist()
    scores = subset['priority_score'].tolist()
    total = subset['bal_num'].sum()
    print(f'  {name} ({count} parcels, ${total:,.0f} total): {apns}')

print()
print('=== ENTITY TYPE ===')
print(df['entity_type'].value_counts(dropna=False).to_string())

print()
print('=== OWNERSHIP CLASS ===')
print(df['ownership_class'].value_counts(dropna=False).to_string())

print()
print('=== REDEMPTION STATUS ===')
print(df['redemption_status'].value_counts(dropna=False).to_string())

print()
print('=== DELINQUENT YEARS ===')
df['years_num'] = pd.to_numeric(df['years_since_power_to_sell'], errors='coerce')
print(df['years_num'].describe().to_string())

print()
print('=== DISTRESS SIGNALS ===')
dist_count = df['distress_signal_score'].astype(float).describe()
print(dist_count.to_string())

print()
print('=== OWNER STATES ===')
print(df['owner_state'].value_counts(dropna=False).head(15).to_string())

print()
print('=== OUT OF STATE? ===')
print(df['out_of_state'].value_counts(dropna=False).to_string())

print()
print('=== INSTALLMENT PLAN ===')
print(df['installment_plan_active'].value_counts(dropna=False).to_string())

print()
print('=== FLOOD / FIRE ZONE ===')
print('Flood zones:', df['flood_zone'].value_counts(dropna=False).head(5).to_dict())
print('Fire zones:', df['fire_hazard_zone'].value_counts(dropna=False).head(5).to_dict())
