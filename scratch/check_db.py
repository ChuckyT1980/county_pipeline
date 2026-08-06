import sqlite3, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent.parent

db = BASE / 'tax_pipeline' / 'cps1_outcomes.db'
conn = sqlite3.connect(str(db))
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('=== CPS-1 DB TABLES ===')
for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
    print(f"  {t[0]}: {count} rows")

try:
    ve = pd.read_sql("SELECT verification_status, COUNT(*) as n FROM verification_events GROUP BY verification_status", conn)
    print('\n=== VERIFICATION STATUS IN DB ===')
    print(ve.to_string(index=False))
except Exception as e:
    print(f'verification_events error: {e}')

try:
    sample = conn.execute("SELECT lead_id FROM verification_events LIMIT 10").fetchall()
    print('\n=== SAMPLE LEAD IDs ===')
    for row in sample:
        print(' ', row[0])
except Exception as e:
    print(f'lead_id sample error: {e}')

conn.close()

# Now check if master CSV lead_ids match DB lead_ids
print('\n=== MASTER CSV vs DB JOIN CHECK ===')
import re
master = pd.read_csv(BASE / 'northern_ca_MASTER_merged.csv')

def fmt_apn(a):
    digits = re.sub(r'\D', '', str(a))
    digits = digits.zfill(12)
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}"

def make_lead_id(row):
    county = str(row.get('county', '')).strip().capitalize()
    for field in ['fee_parcel', 'apn', 'apn_pdf', 'asmt']:
        v = row.get(field, '')
        if v and str(v).strip() not in ('', 'nan', 'None'):
            return f"{county}_{fmt_apn(str(v))}"
    return None

master['lead_id'] = master.apply(make_lead_id, axis=1)

conn2 = sqlite3.connect(str(db))
try:
    db_ids = set(r[0] for r in conn2.execute("SELECT DISTINCT lead_id FROM verification_events").fetchall())
    master_ids = set(master['lead_id'].dropna().tolist())
    matches = master_ids & db_ids
    print(f"Master lead IDs:      {len(master_ids)}")
    print(f"DB verification IDs:  {len(db_ids)}")
    print(f"Matching (join hits): {len(matches)}")
    print(f"Master IDs not in DB: {len(master_ids - db_ids)}")
    if matches:
        print("Sample matched IDs:", list(matches)[:5])
except Exception as e:
    print(f'Join check error: {e}')
conn2.close()
