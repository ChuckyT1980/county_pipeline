import sqlite3
from core.county import CountyConfig
db = sqlite3.connect('data/counties/fresno/state.sqlite')
print("=== tax_deed=yes parcels ===")
for r in db.execute("SELECT apn, owner, former_owner, tax_deed FROM parcels WHERE tax_deed='yes'"):
    print(r)
cfg = CountyConfig.load('fresno')
print("collector_names:", cfg.collector_names)
