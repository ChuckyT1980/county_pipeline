import csv
import json
import time
from connectors.tehama import TehamaConnector


def merge(distress_event, property_snapshot):
    return {
        "entity_key": f"tehama|{distress_event['apn'].replace('-', '')}",
        "property_core": {
            "apn": distress_event["apn"],
            "apn_normalized": distress_event["apn"].replace("-", ""),
            "county": "tehama"
        },
        "distress_event": distress_event,
        "property_snapshot": property_snapshot
    }

def run_merge_pipeline():
    connector = TehamaConnector(county="tehama")
    merged_leads = []
    
    print("[START] Running Merge Engine on Distress Signals...")
    
    with open("tehama_tax_default_leads.csv", "r") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
                
            apn = row["apn"]
            distress_event = {
                "apn": apn,
                "source": "tax_delinquency_notice",
                "amount_due": float(row["amount_due"]),
                "default_year": int(row["default_year"]),
                "notice_date": "2025-06",
                "event_type": "impending_default",
                "raw_owner_signal": row["name_address_raw"]
            }
            
            result = connector.run(apn)
            
            merged = merge(distress_event, result.get("snapshot", {}))
            merged_leads.append(merged)
            
            print(f"Merged: {merged['entity_key']} -> Situs: {merged['property_snapshot'].get('situs_address') if merged['property_snapshot'] else 'NOT FOUND'}")
            time.sleep(0.5)

    with open("unified_leads_sample.json", "w") as f:
        json.dump(merged_leads, f, indent=2)
        
    print(f"[DONE] Merged {len(merged_leads)} entity records.")

if __name__ == "__main__":
    run_merge_pipeline()
