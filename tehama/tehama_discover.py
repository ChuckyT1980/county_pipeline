import requests
import json
import pandas as pd
import time
import os

URL = "https://services2.arcgis.com/3iNbxbY9zhyxPvde/arcgis/rest/services/Tehama_County_Parcels_2025_11_04/FeatureServer/0/query"

all_records = []
offset = 0
chunk_size = 2000

print("Pulling Tehama Master Parcel Index from Official GIS Server...")

while True:
    params = {
        "where": "1=1",
        "outFields": "LOWPARCELI,Situs1",
        "returnGeometry": "false",
        "f": "json",
        "resultOffset": offset,
        "resultRecordCount": chunk_size
    }
    
    r = requests.get(URL, params=params)
    if r.status_code != 200:
        print(f"Error fetching data: HTTP {r.status_code}")
        break
        
    data = r.json()
    features = data.get("features", [])
    
    if not features:
        break
        
    for f in features:
        attrs = f.get("attributes", {})
        apn = attrs.get("LOWPARCELI")
        situs = attrs.get("Situs1")
        
        if apn:
            all_records.append({
                "parcel_number": apn,
                "address": situs
            })
            
    print(f"Fetched {len(all_records)} records...")
    
    if len(features) < chunk_size:
        break
        
    offset += chunk_size
    time.sleep(0.5)

df = pd.DataFrame(all_records)
df = df.drop_duplicates(subset=["parcel_number"])
out_path = os.path.join(os.path.dirname(__file__), "tehama_AUTHORITATIVE_master_index.csv")
df.to_csv(out_path, index=False)

print(f"\nSUCCESS: Saved {len(df)} unique parcels to {out_path}")
