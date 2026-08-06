import sys
sys.path.insert(0, '.')
from core.county import CountyConfig
from core.state import StateStore

store = StateStore(CountyConfig.load('tehama'))
rows = store.conn.execute("SELECT apn FROM parcels WHERE tax_verified_url != ''").fetchall()
for (apn,) in rows:
    store.mark_known(apn, 'tax_verified_url', commit=False)
    store.mark_known(apn, 'tax_verified_at', commit=False)
store.commit()
print('marked known:', len(rows))
store.close()
