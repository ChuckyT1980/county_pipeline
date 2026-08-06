"""
Apply all 5 lead_pipeline_fixes to the current combined export.
"""
import pandas as pd, os
from pathlib import Path
from lead_pipeline_fixes import *

BASE = Path(__file__).parent

# Load combined export
df = pd.read_csv(BASE / "northern_ca_export_ready.csv")
print(f"Loaded: {len(df)} leads\n")

# 1. Owner name backfill
df = resolve_owner_name(df)
src = df["owner_name_source"].value_counts()
print(f"1. Owner name source:\n   {src.to_string().replace(chr(10), chr(10)+'   ')}\n")

# 2. Entity classification
df = classify_entity_owner(df)
ent = df["is_entity"].value_counts()
print(f"2. Entity owners: {ent.to_dict()}\n")

# 3. Clean title
df = flag_clean_title(df)
ct = df["clean_title"].value_counts()
print(f"3. Clean title: {ct.to_dict()}\n")

# 4. Recorder doc audit
print("4. Recorder doc coverage:")
cov = audit_recorder_doc_coverage(df)
print(f"   {cov.to_string().replace(chr(10), chr(10)+'   ')}\n")

# 5. Diff check (compare old vs new combined export if old exists)
old_path = BASE / "northern_ca_MASTER_export_with_owners.csv"
if os.path.exists(old_path):
    print("5. Diff (MASTER_export_with_owners -> export_ready):")
    result = diff_exports(old_path, BASE / "northern_ca_export_ready.csv")
    for k, v in result.items():
        if len(v):
            print(f"   {k}: {len(v)} rows")
            if "total_balance" in v.columns:
                print(f"      total_balance: ${pd.to_numeric(v['total_balance'], errors='coerce').sum():,.0f}")
            if "owner_name" in v.columns:
                for _, r in v.head(3).iterrows():
                    print(f"      {r.get('apn','?')}  {r['owner_name'][:35]}")
        else:
            print(f"   {k}: 0 rows")

# Save enriched export
out = BASE / "northern_ca_export_ready.csv"
df.to_csv(out, index=False)
print(f"\nSaved enriched export: {out}")
