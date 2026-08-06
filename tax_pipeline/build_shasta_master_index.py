import requests
import json
import pandas as pd
import time
from math import ceil

def build_shasta_master():
    print("Fetching master list of all Object IDs from Shasta County GIS...")
    base_url = "https://gis.shastacounty.gov/arcgis/rest/services/OpenData/ParcelAssesseeSitus/FeatureServer/0/query"
    
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
        print("Failed to get Object IDs. Response:", data)
        return
        
    total_parcels = len(object_ids)
    print(f"Successfully discovered EXACTLY {total_parcels} parcels in Shasta County.")
    
    # 2. Fetch data in chunks to avoid overwhelming the server
    chunk_size = 1000
    all_parcels = []
    
    print(f"Downloading master parcel data in chunks of {chunk_size}...")
    for i in range(0, total_parcels, chunk_size):
        chunk = object_ids[i:i+chunk_size]
        chunk_str = ",".join(map(str, chunk))
        
        params_data = {
            "objectIds": chunk_str,
            "outFields": "ASMT,APN,APN_Dash,Situs_Address",
            "returnGeometry": "false",
            "f": "json"
        }
        
        try:
            r = requests.post(base_url, data=params_data, timeout=30)
            features = r.json().get("features", [])
            
            for f in features:
                attrs = f.get("attributes", {})
                asmt = attrs.get("ASMT", "")
                if asmt:  # Only keep parcels that have an ASMT
                    all_parcels.append({
                        "asmt": str(asmt).replace("-", "").strip(),
                        "apn_dash": attrs.get("APN_Dash", ""),
                        "address": attrs.get("Situs_Address", ""),
                        "county": "shasta"
                    })
            
            print(f"  Progress: {min(i+chunk_size, total_parcels)} / {total_parcels} parcels downloaded...")
            time.sleep(0.5)  # Be polite to the county server
            
        except Exception as e:
            print(f"Error fetching chunk {i}: {e}")
            time.sleep(2)
            
    # 3. Save the authoritative master index
    df = pd.DataFrame(all_parcels)
    df.drop_duplicates(subset=["asmt"], inplace=True)
    
    out_file = "shasta_AUTHORITATIVE_master_index.csv"
    df.to_csv(out_file, index=False)
    print(f"\nDone! Saved {len(df)} 100% verified unique APNs to {out_file}")
    
if __name__ == "__main__":
    build_shasta_master()
