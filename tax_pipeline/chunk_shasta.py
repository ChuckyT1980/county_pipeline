import pandas as pd
import sqlite3
import os

print("Chunking 5,000 unverified parcels for Shasta...")

# 1. Load the full master index
master_csv = "shasta_AUTHORITATIVE_master_index.csv"
if not os.path.exists(master_csv):
    print(f"Error: {master_csv} not found")
    exit(1)
    
df_master = pd.read_csv(master_csv, dtype=str)

# 2. Connect to global cache to filter out already verified
conn = sqlite3.connect("cps1_outcomes.db")
cursor = conn.cursor()
cursor.execute("SELECT asmt FROM global_verifications WHERE county='shasta'")
verified_set = set(row[0] for row in cursor.fetchall())
conn.close()

# 3. Filter unverified
unverified_df = df_master[~df_master['asmt'].isin(verified_set)]

if unverified_df.empty:
    print("All parcels in the master index have already been verified!")
    exit(0)

# 4. Take the next 5,000
chunk_size = 5000
chunk_df = unverified_df.head(chunk_size)

out_file = "shasta_chunk_5000.csv"
chunk_df.to_csv(out_file, index=False)

print(f"Total unverified remaining: {len(unverified_df)}")
print(f"Saved next {len(chunk_df)} parcels to {out_file} for verification.")
