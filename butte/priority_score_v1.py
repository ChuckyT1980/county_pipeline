import pandas as pd
import json
import math

def determine_entity_type(name: str) -> str:
    if not name: return ""
    name_upper = name.upper()
    if any(x in name_upper for x in [" LLC", "L.L.C."]): return "LLC"
    if any(x in name_upper for x in [" INC", "CORP", "COMPANY"]): return "CORPORATION"
    if any(x in name_upper for x in [" TRUST", " TR "]): return "TRUST"
    if any(x in name_upper for x in [" ESTATE "]): return "ESTATE"
    return "INDIVIDUAL"

def extract_owner_info(row):
    chain_str = row.get("recorder_chain", "[]")
    if pd.isna(chain_str):
        chain_str = "[]"
    try:
        chain = json.loads(chain_str)
    except:
        chain = []
    
    primary_name = ""
    if chain:
        evt = chain[0]
        grantee = evt.get("grantees", [])
        grantor = evt.get("grantors", [])
        primary_name = grantee[0] if grantee else (grantor[0] if grantor else "")
        
    return primary_name, determine_entity_type(primary_name), 0.9 if primary_name else 0.0

def compute_score(balance):
    # 0 to 50k maps linearly to 50 - 80
    # 50k+ maps logarithmically to 80 - 100
    if balance <= 0:
        return 50.0
    if balance <= 50000:
        return round(50.0 + 30.0 * (balance / 50000.0), 1)
    
    # above 50k, log scale up to roughly 2.5M
    # log10(50,000) = 4.698
    # log10(2,500,000) = 6.397
    # span = 6.397 - 4.698 = 1.699
    
    base_log = math.log10(50000)
    max_log = math.log10(2500000)
    
    val_log = math.log10(balance)
    
    # Cap at 2.5M for the 100 limit
    if val_log > max_log:
        return 100.0
        
    log_pct = (val_log - base_log) / (max_log - base_log)
    return round(80.0 + 20.0 * log_pct, 1)

def main():
    input_csv = "butte_auction_105_ENRICHED.csv"
    output_csv = "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"
    
    df = pd.read_csv(input_csv, dtype=str)
    
    # Keep any manual overrides that were placed in the existing call sheet (like Frank Tatum)
    existing_overrides = {}
    if pd.io.common.file_exists(output_csv):
        old_df = pd.read_csv(output_csv, dtype=str)
        for _, r in old_df.iterrows():
            if pd.notna(r.get('notes')) and 'Manually verified' in str(r.get('notes')):
                existing_overrides[str(r['apn'])] = {
                    'name': str(r['verified_current_owner_name']),
                    'type': str(r['entity_type']),
                    'conf': str(r['owner_vesting_confidence']),
                    'notes': str(r['notes'])
                }
    
    out_rows = []
    for _, row in df.iterrows():
        balance_str = row.get("total_defaulted_balance", "0")
        try:
            balance = float(balance_str)
        except:
            balance = 0.0
            
        score = compute_score(balance)
        apn = row.get("auction_apn_dashed", row.get("parcel_number", ""))
        
        owner_name, entity_type, confidence = extract_owner_info(row)
        notes = ""
        
        # Apply manual overrides
        if apn in existing_overrides:
            owner_name = existing_overrides[apn]['name']
            entity_type = existing_overrides[apn]['type']
            confidence = float(existing_overrides[apn]['conf'])
            notes = existing_overrides[apn]['notes']
        
        out_rows.append({
            "priority_score": score,
            "verified_current_owner_name": owner_name,
            "entity_type": entity_type,
            "situs_address": "",
            "v_total_balance": f"${balance:,.2f}",
            "apn": apn,
            "owner_vesting_confidence": confidence,
            "priority_score_note": f"Log scaled over 50k. Orig: {balance}",
            "phone_number": "",
            "mailing_address": "",
            "call_date_1": "",
            "outcome_1": "",
            "call_date_2": "",
            "outcome_2": "",
            "next_action": "",
            "notes": notes
        })
        
    out_df = pd.DataFrame(out_rows)
    out_df = out_df.sort_values(by="priority_score", ascending=False)
    out_df.to_csv(output_csv, index=False)
    
    print("\n--- SAMPLE OF TOP 7 SCORES (LOG-SCALED) ---")
    print(out_df[['apn', 'v_total_balance', 'priority_score', 'verified_current_owner_name']].head(7).to_string(index=False))
    
if __name__ == '__main__':
    main()
