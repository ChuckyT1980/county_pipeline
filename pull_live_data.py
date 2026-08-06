import requests, json, time

shasta_apns = [
    ("Mullins", "102450028000"), ("Corrigan 1", "107300018000"), ("Corrigan 2", "107300038000"),
    ("Lear", "091300009000"), ("Krieg 1", "031200004000"), ("Krieg 2", "035500008000"),
    ("Truenorth", "064100031000"), ("Pelayo", "073200007000"), ("Clark", "061350004000"),
    ("Kutras 1", "102150010000"), ("Kutras 2", "102150007000"), ("Kutras 3", "102150011000"),
    ("Breeze Capital", "075200019000"), ("Sarab Loh", "107050013000")
]

tehama_apns = [
    ("Toerpe", "103040024000"), ("Nowak", "073260053000"), ("Hanover", "60050021000"),
    ("Soto", "60130002000"), ("McKean", "007130068000"), ("Mathues", "047230014000"),
    ("Blanco", "6320006000"), ("Leigh", "075250043000"),
    ("Joachim 1", "021230006000"), ("Joachim 2", "021230001000"),
    ("Peralta 1", "013220002000"), ("Peralta 2", "013220005000"), ("Peralta 3", "013390059000")
]

headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}

print("\n=== SHASTA LIVE PORTAL DATA ===\n")

for name, apn in shasta_apns:
    url = f"https://common2.mptsweb.com/MBC/api/search/shasta/0000-CURR/feeparcel/{apn}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            rows = data.get("Table", {}).get("Row", [])
            if isinstance(rows, dict): rows = [rows]
            if rows:
                row = rows[0]
                due = row.get("CurrDue", "N/A")
                owner = row.get("OwnerName", "N/A")
                print(f"{name:<20} APN {apn:<15} Due: ${due:<10}  Owner: {owner}")
            else:
                print(f"{name:<20} APN {apn:<15} No data returned")
        else:
            print(f"{name:<20} APN {apn:<15} HTTP {r.status_code}")
    except Exception as e:
        print(f"{name:<20} APN {apn:<15} ERROR: {e}")
    time.sleep(0.3)

print("\n=== TEHAMA LIVE PORTAL DATA ===\n")

for name, apn in tehama_apns:
    url = f"https://common1.mptsweb.com/MBC/api/search/tehama/0000-CURR/feeparcel/{apn}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            rows = data.get("Table", {}).get("Row", [])
            if isinstance(rows, dict): rows = [rows]
            if rows:
                row = rows[0]
                due = row.get("CurrDue", "N/A")
                owner = row.get("OwnerName", "N/A")
                print(f"{name:<20} APN {apn:<15} Due: ${due:<10}  Owner: {owner}")
            else:
                print(f"{name:<20} APN {apn:<15} No data returned")
        else:
            print(f"{name:<20} APN {apn:<15} HTTP {r.status_code}")
    except Exception as e:
        print(f"{name:<20} APN {apn:<15} ERROR: {e}")
    time.sleep(0.3)

print("\n=== DONE ===")
