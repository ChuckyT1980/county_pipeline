import pandas as pd

call_sheet_file = "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"
df = pd.read_csv(call_sheet_file, dtype=str)
idx = df.index[df['apn'] == '027-290-021-000'].tolist()

if idx:
    i = idx[0]
    df.at[i, 'verified_current_owner_name'] = 'TATUM FRANK L'
    df.at[i, 'entity_type'] = 'INDIVIDUAL'
    df.at[i, 'owner_vesting_confidence'] = '1.0'
    df.at[i, 'notes'] = 'Manually verified via public county records (web search)'
    df.to_csv(call_sheet_file, index=False)
    print("Updated 027-290-021-000 with TATUM FRANK L")
else:
    print("APN not found")
