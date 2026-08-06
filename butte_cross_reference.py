import pandas as pd

# Load your current delinquent Butte parcels
delinquent = pd.read_csv('butte/butte_15_percent_sample_VERIFIED.csv', low_memory=False)
delinquent = delinquent[delinquent['v_delinquent'] == True].copy()

# Load the auction history (adjust path to where it actually is)
auction = pd.read_csv('tax_pipeline/butte_all_auction_parcels.csv', low_memory=False)

# Normalize APN formats for matching
def normalize_apn(apn):
    if pd.isna(apn):
        return ''
    return str(apn).replace('-', '').replace(' ', '').strip().zfill(12)

delinquent['apn_norm'] = delinquent['apn_dash'].apply(normalize_apn)
auction['apn_norm'] = auction['apn'].apply(normalize_apn)

# Cross-reference: find delinquent parcels with auction history
auction_history = auction.groupby('apn_norm').agg(
    times_at_auction=('year', 'count'),
    years_at_auction=('year', lambda x: sorted(x.unique().tolist())),
    last_auction_year=('year', 'max'),
    times_redeemed=('status', lambda x: (x.astype(str).str.upper() == 'REDEEMED').sum()),
    times_sold=('status', lambda x: (x.astype(str).str.upper() == 'SOLD').sum()),
    last_status=('status', 'last'),
    min_bid_last=('min_bid', 'last'),
).reset_index()

# Merge
matched = delinquent.merge(auction_history, on='apn_norm', how='inner')

# Score boost: parcels with prior auction history
matched['repeat_distress'] = matched['times_at_auction'] > 1
matched['redeemed_before'] = matched['times_redeemed'] > 0
matched['was_sold_before'] = matched['times_sold'] > 0

# Sort by highest distress signal
matched = matched.sort_values(['times_at_auction', 'v_total_balance'], ascending=False)

# Save results
matched.to_csv('butte/butte_repeat_distress_leads.csv', index=False)

# Print summary
print(f"Total current delinquent parcels: {len(delinquent)}")
print(f"Matched with auction history: {len(matched)}")
print(f"Repeat distress (2+ auctions): {matched['repeat_distress'].sum()}")
print(f"Previously redeemed (paid last minute): {matched['redeemed_before'].sum()}")
print(f"Previously sold at auction: {matched['was_sold_before'].sum()}")
print()
print("=== TOP 10 PRIORITY LEADS ===")
cols = ['apn_dash', 'address', 'v_total_balance', 'times_at_auction', 
        'years_at_auction', 'times_redeemed', 'last_status']
print(matched[cols].head(10).to_string(index=False))
