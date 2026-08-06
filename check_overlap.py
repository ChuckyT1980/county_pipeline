import sqlite3
import pandas as pd
import re

con = sqlite3.connect('data/counties/humboldt/state.sqlite')
df_sqlite = pd.read_sql_query("SELECT apn, owner, tax_deed FROM parcels WHERE tax_deed = 'yes'", con)
con.close()

df_csv = pd.read_csv('data/counties/humboldt/excess_proceeds.csv')

print('SQLite tax_deed=yes count:', len(df_sqlite))
print('SQLite sample APNs:', df_sqlite['apn'].head(5).tolist())

print('CSV row count:', len(df_csv))
print('CSV sample APNs:', df_csv['apn'].head(5).tolist())

def clean(x): return re.sub(r'[^0-9]', '', str(x)).zfill(12)

sql_apns = set(df_sqlite['apn'].apply(clean))
csv_apns = set(df_csv['apn'].apply(clean))

common = sql_apns.intersection(csv_apns)
print('Common APNs count:', len(common))
if common:
    print('Sample common APNs:', list(common)[:5])

print('CSV APNs not in SQLite tax_deed=yes:', len(csv_apns - sql_apns))
print('SQLite tax_deed=yes APNs not in CSV:', len(sql_apns - csv_apns))
