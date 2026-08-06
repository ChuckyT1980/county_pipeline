#!/usr/bin/env python3
import sys
import subprocess
import glob
import os
import pandas as pd

if len(sys.argv) < 2:
    print("Usage: python run_county.py <county> [book]")
    sys.exit(1)

county = sys.argv[1].lower()
book = sys.argv[2] if len(sys.argv) > 2 else "35"

# Counties that don't use the MPTS API — skip gracefully
MPTS_ONLY = ['lassen', 'butte']  # These 404 on mptsweb.com
if county in MPTS_ONLY:
    print(f"\n=== {county.upper()} uses EagleWeb portal — MPTS batch not supported yet ===")
    print("Skipping. Run manually via stage1_discover_shasta.py equivalent when ready.")
    sys.exit(0)  # Exit 0 so checkpoint marks as done and doesn't retry

print(f"\n=== Running {county.upper()} book {book} ===\n")

# Stage 1: Discovery
if county == "shasta":
    subprocess.run(f"python -m tax_pipeline.test_discovery_mpts {county} {book}", shell=True)
else:
    subprocess.run(f"python -m tax_pipeline.test_discovery_mpts {county} {book}", shell=True)

# Find the discovery file (root dir for MPTS)
files = sorted(glob.glob(f"{county}_test_book*{int(book):03d}_*.csv"), key=os.path.getmtime, reverse=True)
if not files:
    files = sorted(glob.glob(f"tax_pipeline/{county}_test_book*{book}_*.csv"), key=os.path.getmtime, reverse=True)
if not files:
    files = sorted(glob.glob(f"tax_pipeline/{county}_discovery_*.csv"), key=os.path.getmtime, reverse=True)

if not files:
    print("No discovery file found — exiting")
    sys.exit(1)

discovery = files[0]

# Check discovery has real data
try:
    disc_df = pd.read_csv(discovery)
    if len(disc_df) == 0:
        print(f"Discovery file empty ({discovery}) — skipping book")
        sys.exit(0)  # Exit 0 — empty book, mark as done
except Exception as e:
    print(f"Cannot read discovery file: {e}")
    sys.exit(1)

print(f"Using discovery file: {discovery} ({len(disc_df)} parcels)")

# Stage 2: Verify
subprocess.run(f"python -m tax_pipeline.stage2_verify {county} {discovery}", shell=True)

# Find the most recent CRM output and check it has rows
if county == "shasta":
    subprocess.run("python fill_shasta_owners.py", shell=True)
    crm_files = sorted(glob.glob("shasta_crm*_with_owners.csv"), key=os.path.getmtime, reverse=True)
else:
    crm_files = sorted(glob.glob(f"{county}_crm_*.csv"), key=os.path.getmtime, reverse=True)

if crm_files:
    try:
        crm_df = pd.read_csv(crm_files[0])
        if len(crm_df) > 0:
            if county == "shasta":
                crm_df.to_csv("tax_pipeline/shasta_MASTER_leads_with_liens.csv", index=False)
                subprocess.run("python filter_shasta_leads.py", shell=True)
                import shutil
                filtered = "tax_pipeline/shasta_MASTER_leads_with_liens_filtered.csv"
                if os.path.exists(filtered):
                    shutil.copy(filtered, "tax_pipeline/shasta_MASTER_leads_with_liens.csv")
            else:
                crm_df.to_csv(f"tax_pipeline/{county}_MASTER_leads_with_liens.csv", index=False)
            print(f"Promoted {len(crm_df)} leads to MASTER")
        else:
            print(f"CRM file has 0 rows — MASTER not updated (DNS failures during verify likely cause)")
    except Exception as e:
        print(f"CRM promotion error: {e}")
else:
    print("No CRM file found — stage2 may have failed")

# Stage 7: Recorder enrichment
subprocess.run(f"python -m tax_pipeline.stage7_recorder_enrich {county}", shell=True)

print(f"\n=== {county.upper()} book {book} complete ===")
