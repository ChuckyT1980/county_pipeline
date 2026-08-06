import pandas as pd

df = pd.read_csv(r'C:\Users\chuck\Downloads\county_pipeline\kern\kern_REAL_auction_list_fatco.csv')
print(f'TOTAL REAL RECORDS IN FILE: {len(df)}')

# Focus on the real auction columns
auction_cols = ['APN_1','Parcel_Number','County_Name','Owner','Minimum_Bid_Owed',
                'Property_Description','Tax_Year','Parcel_Location','State',
                'ASSESSED_TOTAL_VALUE','ASSESSED_LAND_VALUE','ASSESSED_IMPROVEMENT_VALUE',
                'FLOOD_ZONE_CODE','INSIDE_SFHA']
available = [c for c in auction_cols if c in df.columns]
df_auction = df[available].dropna(subset=['Parcel_Number','Owner','Minimum_Bid_Owed'])
print(f'Real auction parcels with APN+Owner+Bid: {len(df_auction)}')
print()
print(df_auction.head(20).to_string())
print()

# Stats
bids = df_auction['Minimum_Bid_Owed']
print(f'Min bid LOW:  ${bids.min():,.0f}')
print(f'Min bid HIGH: ${bids.max():,.0f}')
print(f'Total exposure: ${bids.sum():,.0f}')

# Save cleaned auction-only CSV
out = r'C:\Users\chuck\Downloads\county_pipeline\kern\kern_REAL_AUCTION_PARCELS_CLEAN.csv'
df_auction.to_csv(out, index=False)
print(f'\nSaved clean file: {out}')
