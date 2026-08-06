"""Apply high-pressure filter to the export"""
import csv, os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(base_dir, 'northern_ca_MASTER_export_with_owners.csv')

rows = list(csv.DictReader(open(path)))
print(f"Total rows: {len(rows)}")

# Filter: delinquent, balance >= $7,500, payment status LATE/DUE, owner known, recorder known
filtered = []
for r in rows:
    try:
        balance = float(r.get('total_balance', 0) or 0)
    except:
        balance = 0
    delinquent = r.get('delinquent', '').strip().lower() == 'true'
    status = r.get('inst1_status', '').strip()
    owner = r.get('owner_name', '').strip()
    recorder = r.get('recorder_info', '').strip()
    
    if (delinquent and balance >= 7500 and status in ('LATE', 'DUE')
        and owner and recorder and owner != 'SKIP_TRACE_REQUIRED'):
        filtered.append(r)

print(f"\nHigh-pressure leads (>= $7,500, delinquent, owner+recorder known): {len(filtered)}")
print()
total_bal = 0
for r in filtered:
    bal = float(r.get('total_balance', 0) or 0)
    total_bal += bal
    county = r.get('county', '?')
    liens = r.get('liens', '?')
    apn = r.get('fee_parcel', r.get('apn', '?'))
    print(f"  {r['owner_name'][:38]:38s} ${bal:>8,.2f}  {county:8s} liens={liens:5s}  {apn}")

print(f"\nTotal balance: ${total_bal:,.2f}")
