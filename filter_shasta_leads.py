#!/usr/bin/env python3
import pandas as pd
import re

df = pd.read_csv('tax_pipeline/shasta_MASTER_leads_with_liens.csv')

# Government / non-sellable entities
gov_patterns = [
    r'\bUNITED STATES\b', r'\bU S A\b', r'\bU\.S\.A\.\b',
    r'\bFOREST SERVICE\b', r'\bCOUNTY OF\b', r'\bSTATE OF\b',
    r'\bCALIFORNIA\b', r'\bDEPARTMENT OF\b', r'\bBUREAU OF\b',
    r'\bMUTUAL WATER\b', r'\bWATER COMPANY\b', r'\bPUBLIC UTILITY\b',
]

def is_gov_or_utility(name):
    if pd.isna(name):
        return True
    name = str(name).upper()
    return any(re.search(p, name) for p in gov_patterns)

# Parse dollar
def parse_dollar(s):
    try:
        return float(re.sub(r'[^\d.]', '', str(s)))
    except:
        return 0.0

df['balance_num'] = df['v_total_balance'].apply(parse_dollar)

# Filter
good = df[
    ~df['assessee_name'].apply(is_gov_or_utility) &
    (df['balance_num'] > 100)
].copy()

print(f"Original: {len(df)}")
print(f"After filtering: {len(good)}")
print(f"\nTop balances:")
print(good[['assessee_name', 'v_total_balance', 'mailing_address']].head(20).to_string(index=False))

good.drop(columns=['balance_num'], errors='ignore', inplace=True)
good.to_csv('tax_pipeline/shasta_MASTER_leads_with_liens_filtered.csv', index=False)
print(f"\nSaved: tax_pipeline/shasta_MASTER_leads_with_liens_filtered.csv")
