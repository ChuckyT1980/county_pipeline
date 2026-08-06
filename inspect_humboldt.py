import sqlite3
con = sqlite3.connect('data/counties/humboldt/state.sqlite')
cur = con.cursor()

cur.execute('SELECT COUNT(*) FROM parcels WHERE values_known = 0 AND [values] IS NULL')
print('NULL values + not known:', cur.fetchone()[0])
cur.execute('SELECT COUNT(*) FROM parcels WHERE values_known = 0 AND [values] IS NOT NULL')
print('Has value but not known:', cur.fetchone()[0])
cur.execute('SELECT COUNT(*) FROM parcels WHERE tax_deed = "yes"')
print('tax_deed=yes:', cur.fetchone()[0])

cur.execute('SELECT * FROM passes ORDER BY rowid DESC LIMIT 5')
cols = [d[0] for d in cur.description]
print()
print('Last 5 passes:')
for row in cur.fetchall():
    print(' ', dict(zip(cols, row)))

con.close()
