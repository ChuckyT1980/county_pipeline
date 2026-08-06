import sqlite3
conn = sqlite3.connect(r'data\counties\tehama\state.sqlite')
conn.row_factory = sqlite3.Row
total = conn.execute('SELECT COUNT(*) FROM parcels').fetchone()[0]
n_nan = conn.execute("SELECT COUNT(*) FROM parcels WHERE owner='nan' OR owner='' OR owner IS NULL").fetchone()[0]
n_own = conn.execute("SELECT COUNT(*) FROM parcels WHERE owner != '' AND owner != 'nan' AND owner IS NOT NULL").fetchone()[0]
print(f'total: {total} | owner nan/empty: {n_nan} | real owners: {n_own}')
for row in conn.execute("SELECT apn, owner, situs FROM parcels WHERE owner != '' AND owner != 'nan' AND owner IS NOT NULL LIMIT 5"):
    print(' ', dict(row))
conn.close()
