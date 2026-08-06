import sqlite3
from pathlib import Path
conn = sqlite3.connect(str(Path(__file__).parent.parent / "scheduler.db"))
cur = conn.cursor()
tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", tables)
for t in tables:
    cols = cur.execute(f"PRAGMA table_info({t[0]})").fetchall()
    print(f"  {t[0]}: columns={[c[1] for c in cols]}")
conn.close()
