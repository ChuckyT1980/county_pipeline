import sys, sqlite3
sys.path.insert(0, '.')
from core.county import CountyConfig

conn = sqlite3.connect(r'data\counties\fresno\state.sqlite')
conn.row_factory = sqlite3.Row
total = conn.execute('SELECT COUNT(*) FROM parcels').fetchone()[0]
print(f'Fresno state: {total:,} parcels\n')

for col in ('owner', 'values', 'situs', 'mailing', 'use'):
    known = conn.execute(f'SELECT COUNT(*) FROM parcels WHERE "{col}_known"=1').fetchone()[0]
    filled = conn.execute(f'SELECT COUNT(*) FROM parcels WHERE "{col}" IS NOT NULL AND "{col}" != \'\'').fetchone()[0]
    print(f'  {col:12s} known={known:>9,}  actually-filled={filled:>9,}  '
          f'({"OK" if known == filled else "MISMATCH!"})')

# owner sanity: how many are real names vs empty/odd
nan_owner = conn.execute("SELECT COUNT(*) FROM parcels WHERE owner='nan' OR owner='' OR owner IS NULL").fetchone()[0]
print(f'\n  owner nan/empty: {nan_owner:,}')

# values sanity: how many parse as numbers
nums = conn.execute("SELECT COUNT(*) FROM parcels WHERE CAST(\"values\" AS INTEGER) > 0").fetchone()[0]
print(f'  values that parse as positive number: {nums:,}')

print('\nsample real rows:')
for row in conn.execute("SELECT apn, owner, \"values\", situs FROM parcels WHERE owner != '' AND \"values\" != '' LIMIT 3"):
    print(' ', dict(row))
print('\nsample empty rows:')
for row in conn.execute("SELECT apn, owner, \"values\", situs FROM parcels WHERE owner='' LIMIT 2"):
    print(' ', dict(row))

# tax_deed status
td = conn.execute('SELECT COUNT(*) FROM parcels WHERE "tax_deed_known"=1').fetchone()[0]
td_yes = conn.execute("SELECT COUNT(*) FROM parcels WHERE tax_deed='yes'").fetchone()[0]
print(f'\ntax_deed known: {td:,} | flagged yes: {td_yes:,}')
conn.close()
