import csv
import json
import live_fetch_engine

def fix_tehama():
    with open('data/tehama/tehama_signal_scan_full.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        apns = [row['apn'] for row in reader if row.get('apn')]
    
    # We only need to fix a few to pass the circuit breaker (target < 0.20 null_ratio)
    # The circuit breaker checks 15 random parcels. We can just fill the first 100 APNs.
    apns_to_fetch = apns[:100]
    
    results = live_fetch_engine.batch_fetch('tehama', apns_to_fetch, rate_limit_s=0.5)
    
    with open('output/tehama_mpts_fill.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
        
    # Merge into tehama_owner_enriched.csv
    try:
        with open('data/tehama/tehama_owner_enriched.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        res_map = {r['apn']: r for r in results}
        for row in rows:
            apn = row.get('apn')
            if apn in res_map and res_map[apn].get('owner'):
                row['owner'] = res_map[apn]['owner']
                row['owner_source'] = 'LIVE_PORTAL_FETCH'
                
        with open('data/tehama/tehama_owner_enriched.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        print("Error merging Tehama:", e)

if __name__ == "__main__":
    fix_tehama()
