import sqlite3
conn = sqlite3.connect('tax_pipeline/cps1_outcomes.db')
cur = conn.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables:', tables)
for t in tables:
    cnt = cur.execute(f'SELECT COUNT(*) FROM [{t}]').fetchone()[0]
    cols = [r[1] for r in cur.execute(f'PRAGMA table_info([{t}])').fetchall()]
    print(f'  {t}: {cnt} rows, cols={cols}')
conn.close()
