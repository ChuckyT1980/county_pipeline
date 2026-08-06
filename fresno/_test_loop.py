import sys, os
sys.path.insert(0, '.')
from core.county import CountyConfig
from core.state import StateStore

cfg = CountyConfig.load('fresno')
db = cfg.data_dir() / "state.sqlite"
if os.path.exists(db):
    os.remove(db)

store = StateStore(cfg)
roll = cfg.roll_path()
import csv
n = 0
with open(roll, newline="", encoding="utf-8-sig") as fp:
    reader = csv.DictReader(fp)
    for row in reader:
        apn = str(row.get("APN") or "").strip().replace("-", "")
        if not apn:
            continue
        store.upsert_parcel(apn, {"situs": str(row.get("SITEADDRESS1") or "")}, commit=False)
        store.mark_known(apn, "situs", commit=False)
        store.upsert_parcel(apn, {"values": str(row.get("TOTAL_ASSESSED_VALUE") or "")}, commit=False)
        store.mark_known(apn, "values", commit=False)
        store.upsert_parcel(apn, {"mailing": str(row.get("ADDRESS1") or "")}, commit=False)
        store.mark_known(apn, "mailing", commit=False)
        store.upsert_parcel(apn, {"use": str(row.get("USE_PRIMARY") or "")}, commit=False)
        store.mark_known(apn, "use", commit=False)
        store.upsert_parcel(apn, {"owner": str(row.get("NAME1") or "")}, commit=False)
        store.mark_known(apn, "owner", commit=False)
        n += 1
        if n % 2000 == 0:
            store.commit()
            print(f"  seeded {n:,}...")
    store.commit()
print('seeded:', store.count())
print()
print('gaps remaining (should be tax_deed, former_owner, auction_status only):')
for g in store.gaps():
    if g['missing'] > 0:
        print(f"  {g['field']:16s} via {g['source']:10s} prio={g['priority']}  missing={g['missing']:,}")
print()
print('next action:', store.next_action())
store.close()
