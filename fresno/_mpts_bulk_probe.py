"""Probe MPTS for bulk/table endpoints (full-roll pulls for Tehama/Shasta)."""
import requests

def probe(base, county):
    h = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json,text/html"}
    paths = [
        f"/api/search/{county}/0000-CURR",
        f"/api/search/{county}/0000-CURR/",
        f"/api/search/{county}",
        f"/api/search/{county}/0000-CURR/allparcels/1",
        f"/api/search/{county}/0000-CURR/parcels/1",
        f"/api/search/{county}/0000-CURR/asmt/",
        f"/api/counties",
    ]
    for p in paths:
        try:
            r = requests.get(base + p, headers=h, timeout=20)
            body = r.text[:160].replace("\n", " ")
            print(f"{r.status_code} {p} -> {body}")
        except Exception as e:
            print(f"ERR {p} -> {type(e).__name__}: {str(e)[:80]}")

print("=== TEHAMA ===")
probe("https://common1.mptsweb.com/MBC", "tehama")
print("\n=== SHASTA ===")
probe("https://common2.mptsweb.com/MBC", "shasta")
