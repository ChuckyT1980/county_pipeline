"""Quick end-to-end test: Stage 1 -> Stage 2 -> Stage 3 on 5 Butte parcels."""
import os, sys, json

import pandas as pd

# Pick 5 delinquent parcels from verified CSV
verified_csv = os.path.join(os.path.dirname(__file__), "..", "butte", "butte_15_percent_sample_VERIFIED.csv")
df = pd.read_csv(verified_csv)
delinquent = df[df["v_delinquent"] == True].head(5).copy()
print(f"Testing {len(delinquent)} parcels: {delinquent['parcel_number'].tolist()}")
print(f"Owner names from Stage 1: {delinquent['owner_name'].tolist()}")

# --- Stage 2: Recorder Enrichment ---
print("\n=== STAGE 2: Recorder Enrichment ===")
sys.path.insert(0, os.path.dirname(__file__))
from stage2_recorder_enrich import run_stage2

# Write subset to temp CSV
tmp_in = os.path.join(os.path.dirname(__file__), "..", "butte", "_test_subset.csv")
tmp_out = tmp_in.replace(".csv", "_ENRICHED.csv")
delinquent.to_csv(tmp_in, index=False)

run_stage2(tmp_in, "butte")

# Output overwrites input since name doesn't match _VERIFIED.csv
enriched = pd.read_csv(tmp_in)
for _, row in enriched.iterrows():
    apn = row["parcel_number"]
    vesting_raw = row.get("owner_vesting", "{}")
    enc_raw = row.get("encumbrance_summary", "{}")
    chain_raw = row.get("recorder_chain", "[]")
    
    try:
        vesting = json.loads(vesting_raw) if isinstance(vesting_raw, str) else {}
    except:
        vesting = {}
    try:
        chain = json.loads(chain_raw) if isinstance(chain_raw, str) else []
    except:
        chain = []
    
    status = vesting.get("ownership_verification_status", "MISSING")
    primary = vesting.get("primary_name", "")
    owner_name = row.get("owner_name", "")
    doc_type = vesting.get("document_type") or ""
    
    print(f"\n  APN: {apn}")
    print(f"    owner_name: {owner_name}")
    print(f"    status: {status}")
    print(f"    primary_name: {primary}")
    print(f"    doc_type: {doc_type}")
    print(f"    chain events: {len(chain)}")

# --- Stage 3: LLM Adjudication ---
print("\n=== STAGE 3: LLM Adjudication ===")
from stage3_adjudicate import TitleAdjudicator

adj = TitleAdjudicator()
for _, row in enriched.iterrows():
    apn = row["parcel_number"]
    try:
        vesting = json.loads(row["owner_vesting"]) if isinstance(row.get("owner_vesting"), str) else {}
    except:
        vesting = {}
    try:
        enc = json.loads(row["encumbrance_summary"]) if isinstance(row.get("encumbrance_summary"), str) else {}
    except:
        enc = {}
    try:
        chain = json.loads(row["recorder_chain"]) if isinstance(row.get("recorder_chain"), str) else []
    except:
        chain = []
    
    record = {
        "apn": apn,
        "assessor_owner_name": row.get("owner_name", ""),
        "vesting": vesting,
        "encumbrance": enc,
        "chain_events": chain,
    }
    
    result = adj.adjudicate_record(record)
    print(f"\n  APN: {apn}")
    print(f"    final_status: {result.final_ownership_status}")
    print(f"    confidence: {result.adjudication_confidence}")
    print(f"    manual_review: {result.manual_review_required}")
    print(f"    reason_codes: {result.reason_codes}")

# Cleanup
for f in [tmp_in]:
    if os.path.exists(f):
        os.remove(f)

print("\n=== DONE ===")
