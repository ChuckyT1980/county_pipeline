import pandas as pd
import glob
from pathlib import Path
import subprocess

crm_files = sorted(glob.glob("shasta_crm_*_with_owners.csv"), key=lambda x: Path(x).stat().st_mtime, reverse=True)
if not crm_files:
    print("No filled CRM files found.")
    exit(1)

crm_path = crm_files[0]
print(f"Loading filled CRM: {crm_path}")
df = pd.read_csv(crm_path)

# Filter out empty names
initial_len = len(df)
df = df.dropna(subset=['assessee_name'])
df = df[df['assessee_name'].str.strip() != '']
print(f"Filtered out {initial_len - len(df)} rows with missing assessee_name. Proceeding with {len(df)} rows.")

out_path = 'tax_pipeline/shasta_MASTER_leads_with_liens.csv'
df.to_csv(out_path, index=False)
print(f"Saved to {out_path}")

print("Running stage7...")
subprocess.run("python -m tax_pipeline.stage7_recorder_enrich shasta", shell=True)
