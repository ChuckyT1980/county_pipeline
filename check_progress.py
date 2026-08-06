#!/usr/bin/env python3
import json
import os

TOTAL_BOOKS = 30
CHECKPOINT_FILE = "batch_checkpoint.json"

if os.path.exists(CHECKPOINT_FILE):
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            completed = json.load(f)
            count = len(completed)
            print(f"Batch Progress: {count} / {TOTAL_BOOKS} books completed ({(count/TOTAL_BOOKS)*100:.1f}%)")
            if count > 0:
                print(f"Most recently finished: {completed[-1]}")
            if count == TOTAL_BOOKS:
                print("\n✅ BATCH IS 100% COMPLETE! You can now run process_leads.py")
    except Exception as e:
        print(f"Error reading checkpoint: {e}")
else:
    print("Batch hasn't finished the first book yet. Check back in a few minutes!")
