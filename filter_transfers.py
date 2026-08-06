#!/usr/bin/env python3
import pandas as pd
from datetime import datetime, timedelta

df = pd.read_csv('all_seller_intent_HIGH.csv')

def is_recent_transfer(row):
    status = str(row.get('ownership_status', '')).lower()
    if 'sold' in status or 'transfer' in status:
        return True

    doc_date = str(row.get('rec_doc_date', ''))
    if doc_date and doc_date not in ['nan', 'None', '']:
        try:
            dt = pd.to_datetime(doc_date)
            if dt.year >= 2024:
                return True
        except:
            pass
    return False

mask = df.apply(is_recent_transfer, axis=1)
removed = df[mask]
clean = df[~mask].copy()

print(f"Removed {len(removed)} recent transfers:")
print(removed[['assessee_name', 'address', 'rec_doc_date', 'ownership_status']].to_string(index=False))

print(f"\nRemaining HIGH intent leads: {len(clean)}")
clean.to_csv('all_seller_intent_HIGH_no_transfers.csv', index=False)

# Make sure we read from leads_for_sale to create the clean 5 leads sample,
# but we have to filter leads_for_sale too!
leads_for_sale = pd.read_csv('leads_for_sale.csv')

def parse_name_simple(name_str):
    name_str = str(name_str).upper()
    if 'LLC' in name_str or 'INC' in name_str or 'TRUST' in name_str or 'CORP' in name_str:
        return name_str
    if ',' in name_str:
        return name_str
    return name_str

# Get APNs of clean leads
clean_apns = clean['apn'].tolist()
if 'fee_parcel' in clean.columns:
    clean_apns.extend(clean['fee_parcel'].dropna().tolist())

# filter leads_for_sale based on APN
lfs_clean = leads_for_sale[leads_for_sale['APN'].isin(clean_apns)]
lfs_clean.to_csv('leads_for_sale_no_transfers.csv', index=False)
lfs_clean.head(5).to_csv('sample_5_clean_leads.csv', index=False)
print("Saved clean files.")
