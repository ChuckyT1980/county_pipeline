import sqlite3
db = sqlite3.connect('data/counties/fresno/state.sqlite')
print('owner checked:', db.execute('SELECT COUNT(*) FROM parcels WHERE owner_checked=1').fetchone()[0])
print('owner known (from roll):', db.execute('SELECT COUNT(*) FROM parcels WHERE owner_known=1').fetchone()[0])
print('owner gaps left:', db.execute('SELECT COUNT(*) FROM parcels WHERE owner_known=0 AND owner_checked=0').fetchone()[0])
print('tax_deed yes:', db.execute("SELECT COUNT(*) FROM parcels WHERE tax_deed='yes'").fetchone()[0])
print('tax_deed no:', db.execute("SELECT COUNT(*) FROM parcels WHERE tax_deed='no'").fetchone()[0])
print('tax_deed checked:', db.execute('SELECT COUNT(*) FROM parcels WHERE tax_deed_checked=1').fetchone()[0])
