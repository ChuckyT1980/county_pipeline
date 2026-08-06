import sqlite3
for c in ['fresno', 'butte', 'shasta', 'tehama']:
    db = sqlite3.connect(f'data/counties/{c}/state.sqlite')
    n = db.execute('SELECT COUNT(*) FROM parcels').fetchone()[0]
    o = db.execute('SELECT COUNT(*) FROM parcels WHERE owner_known=1').fetchone()[0]
    v = db.execute('SELECT COUNT(*) FROM parcels WHERE values_known=1').fetchone()[0]
    d = db.execute('SELECT COUNT(*) FROM parcels WHERE current_doc_number IS NOT NULL AND length(TRIM(current_doc_number))>0').fetchone()[0]
    td = db.execute("SELECT COUNT(*) FROM parcels WHERE tax_deed='yes'").fetchone()[0]
    print(f'{c:8s} total={n:>7,} owner={o:>7,} values={v:>7,} docs={d:>7,} tax_deed_yes={td:>4,}')
    db.close()
