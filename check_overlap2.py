import sqlite3
import pandas as pd
import re

con = sqlite3.connect('data/counties/humboldt/state.sqlite')
df_csv = pd.read_csv('data/counties/humboldt/excess_proceeds.csv', dtype=str)

print("CSV APNs (raw):", df_csv['apn'].tolist()[:5])

def clean(x): return re.sub(r'[^0-9]', '', str(x)).zfill(12)

csv_apns = [clean(a) for a in df_csv['apn'].dropna()]

cur = con.cursor()
for apn in csv_apns[:5]:
    cur.execute("SELECT apn, owner, tax_deed FROM parcels WHERE apn = ?", (apn,))
    row = cur.fetchone()
    print(f"APN {apn} in DB: {row}")

# Check how many of the 30 CSV APNs exist in DB at all
found_in_db = 0
tax_deed_yes = 0
for apn in csv_apns:
    cur.execute("SELECT tax_deed FROM parcels WHERE apn = ?", (apn,))
    row = cur.fetchone()
    if row:
        found_in_db += 1
        if row[0] == 'yes':
            tax_deed_yes += 1

print(f"\nOf 30 CSV APNs:")
print(f"  Found in DB at all: {found_in_db}")
print(f"  With tax_deed = 'yes': {tax_deed_yes}")

con.close()
