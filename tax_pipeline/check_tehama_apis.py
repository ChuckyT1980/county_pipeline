"""Check all Tehama API endpoints for owner/balance data."""
import requests, json

apn = "035470012000"
headers = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}

base = "https://common1.mptsweb.com/MBC/api/search/tehama/0000-CURR"

endpoints = {
    f"feeparcel/{apn}": "Fee Parcel (identity)",
    f"asmt/{apn}": "Assessment (tax info)",
    f"situs/{apn}": "Situs (address search)",
    f"name/ZAPATERO": "Name search",
    f"taxpayer/{apn}": "Taxpayer lookup",
    f"parcel/{apn}": "Parcel info",
    f"owner/{apn}": "Owner info",
    f"taxhistory/{apn}": "Tax history",
    f"appraisal/{apn}": "Appraisal info",
    f"property/{apn}": "Property info",
    f"roll/{apn}": "Roll info",
    f"delinquent/{apn}": "Delinquent info",
    f"bill/{apn}": "Bill info",
}

# Also try the Shasta connector pattern for owner (HTML with owner endpoint)
html_urls = [
    ("Tax Main HTML", f"https://common1.mptsweb.com/MBC/tehama/tax/main/{apn}/2025/0000"),
    ("Tax Main short", f"https://common1.mptsweb.com/MBC/tehama/tax/main/{apn}"),
    ("Tax Summary", f"https://common1.mptsweb.com/MBC/tehama/tax/summary/{apn}"),
]

# Try alternative API hosts
alt_hosts = [
    ("common1", f"https://common1.mptsweb.com/MBC/api/search/tehama/0000-CURR/feeparcel/{apn}"),
    ("tehama county direct", f"https://tehama.mptsweb.com/MBC/api/search/tehama/0000-CURR/feeparcel/{apn}"),
]

print("=== JSON API ENDPOINTS ===")
for path, desc in endpoints.items():
    url = f"{base}/{path}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json() if r.text else {}
            if isinstance(data, str) and data.startswith("{"):
                data = json.loads(data)
            if isinstance(data, dict) and "Table" in data:
                row = data["Table"].get("Row", {})
                if isinstance(row, list):
                    row = row[0] if row else {}
                print(f"[200] {desc:<30} keys: {list(row.keys()) if row else 'EMPTY'}")
            elif isinstance(data, list):
                print(f"[200] {desc:<30} list: {len(data)} items")
            else:
                print(f"[200] {desc:<30} raw: {str(data)[:100]}")
        else:
            print(f"[{r.status_code}] {desc}")
    except Exception as e:
        print(f"[ERR] {desc}: {e}")

print("\n=== HTML ENDPOINTS ===")
for name, url in html_urls:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.string if soup.title else "N/A"
        print(f"[{r.status_code}] {name:<25} {len(r.text):>6}b  title={title[:60]}")
    except Exception as e:
        print(f"[ERR] {name}: {e}")

print("\n=== ALTERNATIVE HOSTS ===")
for name, url in alt_hosts:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"[{r.status_code}] {name:<30} {len(r.text)}b")
    except Exception as e:
        print(f"[ERR] {name}: {e}")
