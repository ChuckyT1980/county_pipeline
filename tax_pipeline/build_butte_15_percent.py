import requests
import json
import pandas as pd
import time

def build_butte_15_percent():
    print("Fetching 15% sample of Butte County GIS...")
    base_url = "https://services.arcgis.com/3t3QfTXFRFX44zo8/arcgis/rest/services/Butte_County_Parcel_Public_Data/FeatureServer/0/query"
    
    # 1. Get all Object IDs
    params_ids = {
        "where": "1=1",
        "returnIdsOnly": "true",
        "f": "json"
    }
    
    r = requests.get(base_url, params=params_ids, timeout=30)
    data = r.json()
    
    object_ids = data.get("objectIds", [])
    if not object_ids:
        print("Failed to get Object IDs.")
        return
        
    # Take exactly 15% of the total
    target_count = int(len(object_ids) * 0.15)
    object_ids = object_ids[:target_count]
    print(f"Targeting {target_count} parcels (15% of county).")
    
    # 2. Fetch data in chunks
    chunk_size = 1000
    all_parcels = []
    
    for i in range(0, target_count, chunk_size):
        chunk = object_ids[i:i+chunk_size]
        chunk_str = ",".join(map(str, chunk))
        
        params_data = {
            "objectIds": chunk_str,
            "outFields": "APN,SitusLong,SITUS",
            "returnGeometry": "false",
            "f": "json"
        }
        
        try:
            r = requests.post(base_url, data=params_data, timeout=30)
            features = r.json().get("features", [])
            
            for f in features:
                attrs = f.get("attributes", {})
                raw_apn = attrs.get("APN", "")
                if raw_apn:
                    asmt = str(raw_apn).replace("-", "").strip()
                    address = attrs.get("SitusLong", "")
                    if not address or address.strip() == "":
                        address = attrs.get("SITUS", "")
                    
                    if asmt:
                        all_parcels.append({
                            "asmt": asmt,
                            "apn_dash": raw_apn,
                            "address": address.strip() if address else "",
                            "county": "butte"
                        })
            
            print(f"  Progress: {min(i+chunk_size, target_count)} / {target_count} parcels downloaded...")
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Error fetching chunk {i}: {e}")
            time.sleep(1)
            
    # 3. Save the 15% sample
    df = pd.DataFrame(all_parcels)
    df.drop_duplicates(subset=["asmt"], inplace=True)
    
    out_file = "butte_15_percent_sample.csv"
    df.to_csv(out_file, index=False)
    print(f"\nDone! Saved {len(df)} APNs to {out_file}")
    
if __name__ == "__main__":
    build_butte_15_percent()
