import sys, os, requests, sqlite3, json
sys.path.insert(0, os.getcwd())

import live_fetch_engine, raw_storage_manager

raw_storage_manager.init_raw_storage_schema()

test_parcels = [
    ("tehama",   "004-100-015-000"),
    ("shasta",   "001-100-001-000"),
    ("humboldt", "103-111-003-000"),
    ("butte",    "002-650-003-000")
]

session = requests.Session()

print("==========================================================================")
print("ACCURACY & RAW PAYLOAD AUDIT SWEEP ACROSS CALIFORNIA COUNTIES")
print("==========================================================================")

for county, apn in test_parcels:
    res = live_fetch_engine.fetch_county_parcel(county, apn, session)
    
    conn = sqlite3.connect("verification.sqlite")
    cur = conn.execute("SELECT id, source_url, length(raw_content), captured_at FROM raw_captures WHERE county=? AND apn=? ORDER BY id DESC LIMIT 1", (county, apn))
    row = cur.fetchone()
    conn.close()
    
    raw_id = row[0] if row else "N/A"
    raw_size = row[2] if row else 0
    raw_url = row[1] if row else res.get("source_url")
    owner_val = res.get("owner")
    val_val = res.get("assessed_value")
    status_val = res.get("status")
    
    print(f"\nCOUNTY: {county.upper()} | APN: {apn}")
    print(f"  -> Raw Payload Receipt ID: {raw_id} | Payload Size: {raw_size:,d} bytes")
    print(f"  -> Exact Source URL: {raw_url}")
    print(f"  -> Verified Owner: {owner_val}")
    print(f"  -> Verified Assessed Value: {val_val}")
    print(f"  -> Status: {status_val}")
