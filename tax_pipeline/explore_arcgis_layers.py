import requests, json

fs_url = "https://services.arcgis.com/3t3QfTXFRFX44zo8/arcgis/rest/services/Butte_County_Parcel_Public_Data/FeatureServer"

# 1. Check FeatureServer root for all available layers
print("=== FeatureServer root ===")
r = requests.get(fs_url, params={"f": "json"}, timeout=15)
fs_data = r.json()
print(f"Layers: {fs_data.get('layers', [])}")
for layer in fs_data.get("layers", []):
    print(f"  Layer {layer['id']}: {layer['name']}")
print(f"Tables: {fs_data.get('tables', [])}")

# 2. Check layer 0 metadata for ALL available fields
print("\n=== Layer 0 fields ===")
layer_url = f"{fs_url}/0"
r = requests.get(layer_url, params={"f": "json"}, timeout=15)
layer_data = r.json()
print(f"Layer name: {layer_data.get('name', '?')}")
print(f"Fields:")
for field in layer_data.get("fields", []):
    name = field["name"]
    ftype = field["type"]
    alias = field.get("alias", "")
    print(f"  {name:40s} type={ftype:20s} alias={alias}")

# 3. Check if there are more layers
for lid in range(1, 10):
    try:
        r = requests.get(f"{fs_url}/{lid}", params={"f": "json"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if "error" not in data:
                print(f"\n=== Layer {lid}: {data.get('name', '?')} ===")
                for field in data.get("fields", []):
                    print(f"  {field['name']:40s} alias={field.get('alias','')}")
    except:
        pass
