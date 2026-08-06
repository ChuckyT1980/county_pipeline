import pandas as pd
import re

df = pd.read_csv('shasta/shasta_real_distress_ADJUDICATED_CRM_READY.csv')

def score_intent(row):
    score = 0
    reasons = []

    if str(row.get('v_delinquent', '')).upper() in ['TRUE', 'YES', '1', 'DELINQUENT', 'LATE', 'DEFAULT']:
        score += 2
        reasons.append('Delinquent Taxes')

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

    distress = str(row.get('distress_signal', '')).upper()
    if distress not in ['', 'NONE', 'NAN']:
        score += 2
        reasons.append(f'Distress Signal: {distress}')

    if str(row.get('ownership_drift_flag', '')).upper() in ['TRUE', '1', 'YES']:
        score += 1
        reasons.append('Ownership Drift Detected')

    if str(row.get('seller_contact_eligible', '')).upper() in ['TRUE', '1', 'YES']:
        score += 1
        reasons.append('Contact Eligible')

    return pd.Series({'SellerIntentScore': score, 'Reasons': ', '.join(reasons)})

df[['SellerIntentScore', 'Reasons']] = df.apply(score_intent, axis=1)

for _, row in df.iterrows():
    print(f"APN: {row.get('apn')}")
    print(f"Delinquent: {row.get('v_delinquent')} | Balance: {row.get('v_total_balance')}")
    print(f"Notice of Default: {row.get('notice_of_default')}")
    print(f"Open Mortgages: {row.get('total_open_mortgages')}")
    print(f"Distress Signal: {row.get('distress_signal')}")
    print("--------------------------------------------------")
    print(f"Final Score: {row['SellerIntentScore']}")
    print(f"Reasons: {row['Reasons']}")
