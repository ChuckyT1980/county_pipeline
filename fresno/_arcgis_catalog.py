import requests, json

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"}

# 1. Enumerate the ArcGIS REST services directory on Fresno's GIS host
for host in ["https://gisprod10.co.fresno.ca.us", "https://gis.co.fresno.ca.us"]:
    try:
        r = requests.get(f"{host}/arcgis/rest/services?f=json", headers=HEADERS, timeout=20)
        print("=== " + host + " ===")
        if r.status_code == 200:
            try:
                data = r.json()
                for folder in data.get("folders", []):
                    print("  FOLDER:", folder)
                for svc in data.get("services", []):
                    print("  SERVICE:", svc.get("name"), svc.get("type"))
            except Exception as e:
                print("  parse err:", str(e)[:100], r.text[:200])
        else:
            print("  status:", r.status_code)
    except Exception as e:
        print(host, "ERR", str(e)[:100])
