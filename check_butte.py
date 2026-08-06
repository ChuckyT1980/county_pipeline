import sqlite3
import pandas as pd

con = sqlite3.connect('data/counties/butte/state.sqlite')
cur = con.cursor()
cur.execute('PRAGMA table_info(parcels)')
print('Butte SQLite parcels columns:', [r[1] for r in cur.fetchall()])

df = pd.read_sql_query("SELECT apn, owner, situs, [values] FROM parcels WHERE owner IS NOT NULL AND owner != '' LIMIT 5", con)
print(df)
con.close()
