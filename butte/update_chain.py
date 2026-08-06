import pandas as pd
import json

enriched_csv = "butte_auction_105_ENRICHED.csv"
call_sheet = "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"

# The documents we just found via Tyler API
docs = [
    {
        "doc_id": "DOCCOR2014-00241752098527",
        "doc_number": "2014-0024175",
        "doc_type": "NOTICE OF POWER TO SELL TAX DEFAULTED PROPERTY",
        "recording_date": "08/05/2014",
        "grantors": ["TATUM FRANK L"],
        "grantees": ["BUTTE COUNTY TAX COLLECTOR"]
    },
    {
        "doc_id": "DOCCOR1984-00300681762573",
        "doc_number": "1984-0030068",
        "doc_type": "DEED",
        "recording_date": "08/22/1984",
        "grantors": ["BLODGETT EDNA MARIE", "BLODGETT CHARLES A"],
        "grantees": ["TATUM FRANK L"]
    }
]

df_enc = pd.read_csv(enriched_csv, dtype=str)
idx_enc = df_enc.index[df_enc['auction_apn_dashed'] == '027-290-021-000'].tolist()
if idx_enc:
    df_enc.at[idx_enc[0], 'recorder_chain'] = json.dumps(docs)
    df_enc.at[idx_enc[0], 'v_document_number'] = '2014-0024175'
    df_enc.to_csv(enriched_csv, index=False)

df_call = pd.read_csv(call_sheet, dtype=str)
idx_call = df_call.index[df_call['apn'] == '027-290-021-000'].tolist()
if idx_call:
    df_call.at[idx_call[0], 'notes'] = 'Verified via Tyler Recorder API (Notice of Power to Sell 2014-0024175)'
    df_call.to_csv(call_sheet, index=False)

print("Updated ENRICHED and CALL SHEET with real Tyler Recorder chain.")
