#!/usr/bin/env python3
"""
Fill Shasta owner names from GIS FeatureServer.
Run AFTER stage2_verify, BEFORE stage7_recorder_enrich.
"""
import sys
import glob
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "tax_pipeline"))
from shasta_feature_server_adapter import clean_apn, query_batch

crm_files = sorted(glob.glob("shasta_crm_*.csv"), key=lambda x: Path(x).stat().st_mtime, reverse=True)
if not crm_files:
    print("No shasta_crm_*.csv found")
    sys.exit(1)

crm_path = crm_files[0]
print(f"Loading {crm_path}")
df = pd.read_csv(crm_path)

# Build ASMT keys
def get_asmt_key(row):
    for col in ["asmt", "fee_parcel", "apn"]:
        if col in row and pd.notna(row[col]):
            return clean_apn(str(row[col]))
    return ""

df["asmt_key"] = df.apply(get_asmt_key, axis=1)
unique_asmts = [a for a in df["asmt_key"].dropna().unique().tolist() if a]

print(f"Querying FeatureServer for {len(unique_asmts)} parcels...")
results = query_batch(unique_asmts, "FS")

# Map owner names back
owner_map = {}
situs_map = {}
mailing_map = {}
for asmt, attrs in results.items():
    owner_map[asmt] = attrs.get("Assessee", "")
    situs_map[asmt] = attrs.get("Situs_Address", "")
    mailing_map[asmt] = attrs.get("Assessee_Address", "")

df["assessee_name"] = df["asmt_key"].map(owner_map)
df["address"] = df["asmt_key"].map(situs_map)
df["mailing_address"] = df["asmt_key"].map(mailing_map)

# Drop temp key
df = df.drop(columns=["asmt_key"], errors="ignore")

filled = df["assessee_name"].notna().sum()
print(f"Filled {filled}/{len(df)} owner names")

output = crm_path.replace(".csv", "_with_owners.csv")
df.to_csv(output, index=False)
print(f"Saved: {output}")
