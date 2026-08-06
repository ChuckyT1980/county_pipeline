import pandas as pd
import json

df = pd.read_csv('butte/butte_test_75_ENRICHED.csv', dtype={'parcel_number': str})
tail = df.iloc[50:75]

for _, row in tail.iterrows():
    chain_raw = row.get('recorder_chain', '[]')
    try:
        chain = json.loads(chain_raw)
    except Exception:
        chain = []
    if chain:
        first = chain[0]
        print(
            f"parcel={row['parcel_number']}  "
            f"doc={first.get('doc_number','')}  "
            f"type={first.get('doc_type','')}  "
            f"grantors={first.get('grantors',[])}  "
            f"grantees={first.get('grantees',[])}"
        )
    else:
        print(
            f"parcel={row['parcel_number']}  EMPTY CHAIN  "
            f"doc_fmt={row.get('doc_fmt','')}  "
            f"error={row.get('error','')}"
        )
