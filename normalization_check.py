import json
import os

def check_normalization(county):
    file_path = f"snapshots/records_{county}_v1.json"
    if not os.path.exists(file_path):
        print(f"Snapshot for {county} not found.")
        return
        
    with open(file_path, "r", encoding="utf-8") as f:
        records = json.load(f)
        
    # We measure against parsed records (with APNs), not empty headers
    leads = [r for r in records if r.get("apn")]
    total_leads = len(leads)
    
    if total_leads == 0:
        print(f"=== {county.upper()} NORMALIZATION METRICS ===")
        print("No parsed leads found.\n")
        return
    
    tier1_leads = [r for r in leads if r.get("tier") == "T1"]
    tier1_count = len(tier1_leads)
    tier1_density = (tier1_count / total_leads * 100)
    
    decd_count = sum(1 for r in leads if "DECEASED" in r["signals"] or "ESTATE" in r["signals"])
    trust_count = sum(1 for r in leads if "TRUST" in r["signals"] or "MULTI_PARTY" in r["signals"])
    
    t1_confidence = [r["confidence"] for r in tier1_leads]
    avg_confidence = (sum(t1_confidence) / tier1_count) if tier1_count > 0 else 0
    
    print(f"=== {county.upper()} NORMALIZATION METRICS ===")
    print(f"Total Parsed Leads : {total_leads}")
    print(f"Tier 1 Leads       : {tier1_count}")
    print(f"Tier 1 Density     : {tier1_density:.1f}%")
    print(f"DECD/EST Frequency : {(decd_count/total_leads*100):.1f}%")
    print(f"TRUST Frequency    : {(trust_count/total_leads*100):.1f}%")
    print(f"T1 Avg Confidence  : {avg_confidence:.1f}\n")

if __name__ == "__main__":
    check_normalization("shasta")
    check_normalization("tehama")
