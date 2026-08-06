import sqlite3
import pandas as pd
import os

db_path = "cps1_outcomes.db"
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
query = """
SELECT 
    county, 
    tax_year, 
    COUNT(asmt) as total_parcels_verified,
    SUM(CASE WHEN verified_score = 'HOT' THEN 1 ELSE 0 END) as hot_leads,
    SUM(CASE WHEN verified_score = 'WARM' THEN 1 ELSE 0 END) as warm_leads
FROM global_verifications 
GROUP BY county, tax_year
"""

df = pd.read_sql_query(query, conn)
print("=" * 60)
print("  GLOBAL PIPELINE VERIFICATION TRACKER")
print("=" * 60)
if df.empty:
    print("No parcels have been cached globally yet. (They will populate as stage 2 runs).")
else:
    print(df.to_string(index=False))
print("=" * 60)
conn.close()
