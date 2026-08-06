"""Probe for public ArcGIS parcel layers in Tehama and Shasta counties."""
import requests, json

def try_arcgis(name, urls):
    print(f"=== {name} ===")
    for u in urls:
        try:
            r = requests.get(u, params={"f": "json"}, timeout=20)
            if r.status_code == 200 and "services" in r.json():
                svcs = r.json()["services"]
                hits = [s for s in svcs if any(k in s["name"].lower() for k in
                        ["parcel", "assessor", "gpu", "property", "tax"])]
                print(f"  {u}")
                for s in hits[:15]:
                    print(f"     {s['name']} ({s['type']})")
            else:
                print(f"  {u} -> {r.status_code} no services")
        except Exception as e:
            print(f"  {u} -> ERR {type(e).__name__}: {str(e)[:70]}")

# Tehama: try common ArcGIS server patterns
try_arcgis("TEHAMA", [
    "https://gis.tehamacountyca.gov/server/rest/services",
    "https://tehamagis.tehamacounty.gov/arcgis/rest/services",
    "https://gis.tehama.ca.gov/server/rest/services",
])

# Shasta
try_arcgis("SHASTA", [
    "https://gis.shastacounty.gov/server/rest/services",
    "https://gis.co.shasta.ca.us/server/rest/services",
    "https://shasta.maps.arcgis.com",
])
