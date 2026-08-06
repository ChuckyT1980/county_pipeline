import pandas as pd
import json

enriched_csv = "butte_auction_105_ENRICHED.csv"
call_sheet = "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"

# Reset enriched CSV
df_enc = pd.read_csv(enriched_csv, dtype=str)
idx_enc = df_enc.index[df_enc['auction_apn_dashed'] == '027-290-021-000'].tolist()
if idx_enc:
    df_enc.at[idx_enc[0], 'recorder_chain'] = json.dumps([])
    df_enc.at[idx_enc[0], 'v_document_number'] = ''
    df_enc.to_csv(enriched_csv, index=False)

# Reset call sheet
df_call = pd.read_csv(call_sheet, dtype=str)
idx_call = df_call.index[df_call['apn'] == '027-290-021-000'].tolist()
if idx_call:
    df_call.at[idx_call[0], 'verified_current_owner_name'] = ''
    df_call.at[idx_call[0], 'entity_type'] = ''
    df_call.at[idx_call[0], 'owner_vesting_confidence'] = '0.0'
    df_call.at[idx_call[0], 'notes'] = ''
    df_call.to_csv(call_sheet, index=False)

print("Reverted Tatum to blank - no verified tie to APN.")
