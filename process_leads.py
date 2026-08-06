import pandas as pd, glob, os, re

print("--- Step 1: Combine Leads ---")
# Find CRM_READY files from all county subfolders
files = glob.glob('**/*_CRM_READY.csv', recursive=True)
print("Found files:", files)

if not files:
    print("ERROR: No CRM_READY files found. Run export_engine.py first.")
    exit(1)

dfs = []
for f in files:
    # Derive county from the folder name (e.g., tehama/... -> tehama)
    county = f.split(os.sep)[0] if os.sep in f else f.split('/')[0]
    df = pd.read_csv(f)
    df['county'] = county
    dfs.append(df)

combined = pd.concat(dfs, ignore_index=True)
combined.to_csv('all_counties_enriched_leads.csv', index=False)
print(f"Combined {len(combined)} leads from {len(files)} file(s)")

print("\n--- Step 2: Score Intent ---")
df = pd.read_csv('all_counties_enriched_leads.csv')

def score_intent(row):
    score = 0
    reasons = []

    # Tax delinquency signals
    if str(row.get('v_delinquent', '')).upper() in ['TRUE', 'YES', '1', 'DELINQUENT', 'LATE', 'DEFAULT']:
        score += 2
        reasons.append('Delinquent Taxes')

    # Tax balance owed
    def parse_bal(s):
        try: return float(re.sub(r'[^\d.]', '', str(s)))
        except: return 0.0

    bal = parse_bal(row.get('v_total_balance'))
    if bal > 1000:
        score += 1
        reasons.append(f'High Tax Balance (${bal:.0f})')
    elif bal > 500:
        score += 0.5
        reasons.append(f'Medium Tax Balance (${bal:.0f})')

    # Ownership drift — title has changed or is ambiguous
    ownership_status = str(row.get('ownership_verification_status', '')).upper()
    if ownership_status == 'RECORDER_SHOWS_NEW_OWNER':
        score -= 10
        reasons.append('Recent Transfer (Manual Review)')
    elif ownership_status == 'AMBIGUOUS_NAME_MATCH':
        score += 1
        reasons.append('Ambiguous Name Match (Review)')
    elif ownership_status == 'MATCHES_ASSESSOR':
        score += 1
        reasons.append('Owner Confirmed by Recorder')
    elif ownership_status == 'VESTING_CHANGED_SAME_CONTROL':
        score += 1
        reasons.append('Trust/LLC Vesting Change (Same Owner)')

    # Encumbrance signals
    mortgages = parse_bal(row.get('total_open_mortgages', 0))
    if mortgages > 0:
        score += 1
        reasons.append(f'{int(mortgages)} Open Mortgage(s)')

    if str(row.get('notice_of_default', '')).upper() in ['TRUE', '1', 'YES']:
        score += 3
        reasons.append('Notice of Default Filed')

    if str(row.get('notice_of_rescission', '')).upper() in ['TRUE', '1', 'YES']:
        score -= 1
        reasons.append('Notice of Rescission (Resolved)')

    # Distress signal from recorder chain
    distress = str(row.get('distress_signal', '')).upper()
    if distress not in ['', 'NONE', 'NAN']:
        score += 2
        reasons.append(f'Distress Signal: {distress}')

    # Ownership drift flag
    if str(row.get('ownership_drift_flag', '')).upper() in ['TRUE', '1', 'YES']:
        score += 1
        reasons.append('Ownership Drift Detected')

    # Seller contact eligible — highest confidence leads
    if str(row.get('seller_contact_eligible', '')).upper() in ['TRUE', '1', 'YES']:
        score += 1
        reasons.append('Contact Eligible')

    return pd.Series({'SellerIntentScore': score, 'Reasons': ', '.join(reasons)})

df[['SellerIntentScore', 'Reasons']] = df.apply(score_intent, axis=1)
df.to_csv('all_seller_intent.csv', index=False)

df_high = df[df['SellerIntentScore'] >= 3].copy()
df_high.to_csv('all_seller_intent_HIGH.csv', index=False)

print(f"Total leads: {len(df)}")
print(f"HIGH intent leads (score >= 3): {len(df_high)}")

print("\n--- Step 3: Format for Sale ---")
# Filter out any placeholder/dummy rows
mask = df_high.get('assessor_owner_name', pd.Series(dtype=str)).str.contains('JOHN SMITH|DUMMY', case=False, na=False)
df_high = df_high[~mask]

def parse_name(name_str):
    name_str = str(name_str).strip()
    if not name_str or name_str.lower() in ['nan', 'none', '']:
        return '', '', ''
    if ',' in name_str:
        parts = name_str.split(',', 1)
        last = parts[0].strip()
        first = parts[1].strip()
        return first, last, name_str
    parts = name_str.split(' ')
    if len(parts) >= 2:
        return parts[0], ' '.join(parts[1:]), name_str
    return '', name_str, name_str

names = df_high['assessor_owner_name'].apply(parse_name)
df_high = df_high.copy()
df_high['FirstName']       = [n[0] for n in names]
df_high['LastName']        = [n[1] for n in names]
df_high['FullName']        = [n[2] for n in names]
df_high['PropertyAddress'] = df_high['situs_address'].fillna('')
df_high['MailingAddress']  = df_high['assessor_mailing_address'].fillna('') if 'assessor_mailing_address' in df_high.columns else ''
df_high['MailingCity']     = ''
df_high['MailingState']    = 'CA'
df_high['MailingZip']      = ''

def fmt_apn(a):
    if pd.isna(a): return ""
    digits = re.sub(r"\D", "", str(a).replace(".0", ""))
    digits = digits.zfill(12)
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}"

df_high['APN']    = df_high['apn'].apply(fmt_apn)
df_high['County'] = df_high['county']

df_high['CountyTaxLink'] = df_high.apply(
    lambda r: f'=HYPERLINK("https://www.{str(r.get("county","")).lower()}county.gov", "View County Record")'
    if pd.notna(r.get('county')) else '', axis=1
)

# Final CRM columns
cols_to_keep = [
    'FirstName', 'LastName', 'FullName',
    'PropertyAddress', 'MailingAddress', 'MailingCity', 'MailingState', 'MailingZip',
    'APN', 'County', 'SellerIntentScore', 'Reasons',
    'ownership_verification_status', 'ownership_drift_reason',
    'total_open_mortgages', 'notice_of_default', 'distress_signal',
    'stage3_status', 'seller_contact_eligible',
    'CountyTaxLink'
]
cols_to_keep = [c for c in cols_to_keep if c in df_high.columns]
out_df = df_high[cols_to_keep]
out_df.to_csv('leads_for_sale.csv', index=False)
print(f"Saved {len(out_df)} formatted leads to leads_for_sale.csv")

print("\n--- Step 4: Quick Sale Package ---")
out_df.head(10).to_csv('sample_10_leads.csv', index=False)
print("Created sample_10_leads.csv")
