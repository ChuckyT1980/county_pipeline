import requests
import json

BASE = "https://common1.mptsweb.com/MBC"

class TehamaClient:
    def __init__(self):
        self.session = requests.Session()
        print(f"Establishing session at {BASE}/tehama/tax/search...")
        r = self.session.get(f"{BASE}/tehama/tax/search")
        if r.status_code != 200:
            print(f"Failed to get session. Status code: {r.status_code}")

    def search(self, field: str, query: str):
        url = f"{BASE}/api/search/tehama/0000-CURR/{field}/{query}"
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
            "Referer": f"{BASE}/tehama/tax/search"
        }
        r = self.session.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
        return {"error": r.status_code}

if __name__ == "__main__":
    client = TehamaClient()
    tests = [
        ("situs", "035-252-021-000"),
        ("situs", "035252021000"),
        ("situs", "1 Main"),
        ("apn", "035-252-021-000"),
        ("apn", "035-252"),
        ("apn", "035252"),
        ("apn", "035"),
        ("assessment", "035-252-021-000"),
        ("owner", "CERON")
    ]

    for field, query in tests:
        print(f"\n--- Testing {field} with query: '{query}' ---")
        try:
            res = client.search(field, query)
            if isinstance(res, list):
                print(f"SUCCESS: {len(res)} results returned.")
                if len(res) > 0:
                    print(f"Sample snippet: {json.dumps(res[0])[:200]}")
            else:
                print(f"FAILED/OTHER: {res}")
        except Exception as e:
            print(f"EXCEPTION: {e}")
