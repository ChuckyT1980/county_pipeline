import sys, os
sys.path.insert(0, '.')
from core.county import CountyConfig
from core.state import StateStore

cfg = CountyConfig.load('tehama')
db = cfg.data_dir() / "state.sqlite"
if os.path.exists(db):
    os.remove(db)

store = StateStore(cfg)

import csv

# 1. Authoritative master index: parcel_number + address (real, full county)
n_master = 0
with open(r'tehama\tehama_AUTHORITATIVE_master_index.csv', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        apn = str(row.get('parcel_number') or '').strip().replace('-', '')
        if not apn:
            continue
        addr = str(row.get('address') or '').strip()
        store.upsert_parcel(apn, {'situs': addr}, commit=False)
        if addr:
            store.mark_known(apn, 'situs', commit=False)
        n_master += 1
        if n_master % 5000 == 0:
            store.commit()
            print(f'  master {n_master:,}...')
store.commit()
print(f'seeded master index: {n_master:,}')

# 2. Verified sample: only mark verification facts that are REAL.
n_ver = 0
with open(r'tehama\tehama_15_percent_sample_VERIFIED.csv', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        apn = str(row.get('parcel_number') or '').strip().replace('-', '')
        url = str(row.get('verified_url') or '').strip()
        ts = str(row.get('verified_at') or '').strip()
        owner = str(row.get('owner_name') or '').strip()
        if not apn:
            continue
        if not (url and ts):
            continue
        vals = {'tax_verified_url': url, 'tax_verified_at': ts}
        store.upsert_parcel(apn, vals, commit=False)
        if owner and owner.lower() != 'nan':
            store.upsert_parcel(apn, {'owner': owner}, commit=False)
            store.mark_known(apn, 'owner', commit=False)
        n_ver += 1
        if n_ver % 2000 == 0:
            store.commit()
            print(f'  verified {n_ver:,}...')
store.commit()
print(f'verified sample: {n_ver:,}')

# 3. CRM-ready: only the 14 real owners.
n_crm = 0
with open(r'tehama\tehama_15_percent_sample_VERIFIED_ENRICHED_CRM_READY.csv', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        apn = str(row.get('apn') or '').strip().replace('-', '')
        owner = str(row.get('verified_current_owner_name') or '').strip()
        if not apn or not owner or owner.lower() == 'nan':
            continue
        store.upsert_parcel(apn, {'owner': owner}, commit=False)
        store.mark_known(apn, 'owner', commit=False)
        n_crm += 1
        if n_crm % 1000 == 0:
            store.commit()
    store.commit()
print(f'crm owners: {n_crm:,}')

store.close()
