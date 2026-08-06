"""Check if Tehama's JSON ASMT API works (separate from HTML pages)."""
import requests, json

apns = ["035470012000", "039180006000", "039312005000", "800001923000"]

for apn in apns:
    url = f"https://common1.mptsweb.com/MBC/api/search/tehama/0000-CURR/asmt/{apn[:11]}"
    r = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }, timeout=10)
    
    data = None
    try:
        data = r.json()
        if isinstance(data, str):
            data = json.loads(data)
    except:
        pass
    
    if data and "Table" in data:
        row = data["Table"].get("Row", {})
        if isinstance(row, list):
            row = row[0] if row else {}
        print(f"APN {apn}: WORKS  -> keys: {list(row.keys())[:10]}")
    else:
        print(f"APN {apn}: FAILED -> HTTP {r.status_code}, body[:200] = {r.text[:200]}")
