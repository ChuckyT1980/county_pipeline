#!/usr/bin/env python3
"""
batch_run.py — Full end-to-end pipeline runner.

Run this ONE command to go from zero to a ready-to-sell lead list:
    python batch_run.py

What it does:
  1. Discovers parcels for each county/book via MPTS API
  2. Verifies tax delinquency status
  3. Fills owner names (Shasta: via GIS FeatureServer)
  4. Filters government/utility entities (Shasta)
  5. Enriches with recorder/lien data via Stage 7
  6. Scores all leads for seller intent
  7. Filters out recent property transfers
  8. Writes leads_for_sale.csv — ready to send to buyers

Checkpoint system: if interrupted, just re-run. Completed books are skipped.
Delete batch_checkpoint.json to start fresh.
"""

import subprocess
import time
import json
import os
import pandas as pd

RUNS = [
    # Tehama — 10 books (MPTS on common1.mptsweb.com — fully working)
    ("tehama", "35"), ("tehama", "64"), ("tehama", "75"),
    ("tehama", "12"), ("tehama", "89"), ("tehama", "45"),
    ("tehama", "52"), ("tehama", "78"), ("tehama", "91"), ("tehama", "23"),

    # Shasta — 10 books (MPTS on common2.mptsweb.com — discovery/verify working,
    #   Stage 7 lien parsing needs fix. Owner names via GIS FeatureServer.)
    ("shasta", "64"), ("shasta", "75"), ("shasta", "89"),
    ("shasta", "91"), ("shasta", "52"), ("shasta", "45"),
    ("shasta", "78"), ("shasta", "12"), ("shasta", "23"), ("shasta", "67"),

    # Lassen — 5 books (NOT on MPTS — will skip gracefully until portal is found)
    ("lassen", "35"), ("lassen", "64"), ("lassen", "75"),
    ("lassen", "12"), ("lassen", "89"),

    # Butte — 5 books (MPTS on common1 — API responds but needs correct book numbers)
    ("butte", "35"), ("butte", "64"), ("butte", "75"),
    ("butte", "12"), ("butte", "89"),
]

CHECKPOINT_FILE = "batch_checkpoint.json"

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_checkpoint(completed):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(list(completed), f)

def run_final_pipeline():
    """Run scoring, transfer detection, and produce the final sales file."""
    print("\n" + "="*60)
    print("FINAL STAGE: Scoring and formatting all leads...")
    print("="*60)

    # Score all leads
    result = subprocess.run("python process_leads.py", shell=True)
    if result.returncode != 0:
        print("WARNING: process_leads.py returned an error. Check output above.")

    # Run transfer detector to flag/remove recent property transfers
    result2 = subprocess.run("python transfer_detector.py", shell=True)
    if result2.returncode != 0:
        print("WARNING: transfer_detector.py returned an error.")

    # Report final counts
    try:
        df = pd.read_csv("leads_for_sale.csv")
        sellable = pd.read_csv("all_seller_intent_HIGH_sellable.csv") if \
            os.path.exists("all_seller_intent_HIGH_sellable.csv") else df

        # Remove dummy leads
        sellable = sellable[sellable.get("FullName", sellable.get("assessee_name", "")) != "SMITH, JOHN"]
        sellable.to_csv("leads_for_sale.csv", index=False)
        sellable.head(5).to_csv("sample_5_clean_leads.csv", index=False)

        print("\n" + "="*60)
        print("PIPELINE COMPLETE")
        print("="*60)
        print("Final sellable leads: %d" % len(sellable))
        if "county" in sellable.columns or "County" in sellable.columns:
            col = "county" if "county" in sellable.columns else "County"
            print("By county:")
            for county, count in sellable[col].value_counts().items():
                print("  %s: %d leads" % (county, count))
        print()
        print("Output files:")
        print("  leads_for_sale.csv        <-- Full sellable list")
        print("  sample_5_clean_leads.csv  <-- Top 5 for buyer preview")
        print("  all_seller_intent_HIGH_sellable.csv  <-- Scored detail")
        print("  transfer_review_queue.csv  <-- Needs manual review")
    except Exception as e:
        print("Could not summarize final output: %s" % e)

# ── MAIN BATCH LOOP ──────────────────────────────────────────────────────────

completed = load_checkpoint()
print("Loaded %d completed runs from checkpoint." % len(completed))
print("Remaining: %d books to run." % (len(RUNS) - len(completed)))

failed = []

for county, book in RUNS:
    run_id = "%s_%s" % (county, book)

    if run_id in completed:
        print("Skipping %s - already complete." % run_id)
        continue

    print("\n=== %s book %s ===" % (county.upper(), book))

    try:
        subprocess.run(
            "python run_county.py %s %s" % (county, book),
            shell=True,
            check=True
        )
        completed.add(run_id)
        save_checkpoint(completed)
        print("Completed %s. Checkpoint saved." % run_id)
    except subprocess.CalledProcessError as e:
        print("FAILED on %s: %s" % (run_id, e))
        failed.append(run_id)
        print("Continuing to next book...")

    time.sleep(2)

# ── FINAL PIPELINE ────────────────────────────────────────────────────────────

print("\n=== ALL BOOKS PROCESSED ===")
if failed:
    print("Failed books (%d): %s" % (len(failed), ", ".join(failed)))
    print("Re-run batch_run.py to retry failed books (checkpoint will skip successful ones).")

run_final_pipeline()
