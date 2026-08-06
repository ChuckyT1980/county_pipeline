"""Quick test: verify 5 Tehama parcels via APIs."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from connectors.tehama import TehamaConnector

conn = TehamaConnector("tehama")

test_apns = [
    "035470012000",  # 960 DIAMOND AVENUE
    "039180006000",  # 235 CONRAD AVENUE
    "039312005000",  # 13600 TRINITY AVENUE
    "800001923000",  # 224 CONRAD AVENUE (DU, multiple years)
]

for apn in test_apns:
    print(f"\n=== {apn} ===")
    identity = conn.fetch_identity(apn)
    print(f"  Identity source: {identity.source}")
    print(f"  Situs: {identity.data.get('Situs1', 'N/A')}")
    print(f"  TRA: {identity.data.get('Tra', 'N/A')}")
    print(f"  RollCat: {identity.data.get('RollCategory', 'N/A')}")

    owner = conn.fetch_owner(apn)
    print(f"  Owner source: {owner.source}")
    print(f"  Owner: {owner.data.get('Owner', 'N/A')}")

    snapshot = conn.fetch_snapshot(apn)
    print(f"  Snapshot source: {snapshot.source}")
    print(f"  OwnerName: {snapshot.data.get('OwnerName', 'N/A')}")
    print(f"  HTML avail: {snapshot.data.get('_html_available', '?')}")
    print(f"  CurrDue: {snapshot.data.get('CurrDue', 'N/A')}")

print("\nDone.")
