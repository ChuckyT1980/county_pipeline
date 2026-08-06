import pandas as pd
import json

df = pd.read_csv('butte/butte_15_percent_sample_ENRICHED.csv')
count = 0
triggers = ['AMBIGUOUS_NAME_MATCH', 'NO_RECORDER_HIT', 'RECORDER_SHOWS_NEW_OWNER']

for _, r in df.iterrows():
    try:
        vesting_str = str(r.get('owner_vesting', '{}'))
        vesting = json.loads(vesting_str)
        if vesting.get('ownership_verification_status') in triggers:
            count += 1
    except:
        pass

print(f"ESCALATION COUNT: {count}")
