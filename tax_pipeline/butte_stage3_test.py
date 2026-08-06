"""Quick Stage 3 test on already-enriched Butte data."""
import os, json

import pandas as pd
import sys
sys.path.insert(0, os.path.dirname(__file__))
from stage3_adjudicate import TitleAdjudicator

enriched = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "butte", "_test_subset.csv"))
print(f"Loaded {len(enriched)} enriched records")

adj = TitleAdjudicator()
for _, row in enriched.iterrows():
    parcel = row["parcel_number"]
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
        "apn": parcel,
        "assessor_owner_name": row.get("owner_name", ""),
        "vesting": vesting,
        "encumbrance": enc,
        "chain_events": chain,
    }

    result = adj.adjudicate_record(record)
    print(f"\n  APN: {parcel}")
    print(f"    owner_name: {row.get('owner_name', '')}")
    print(f"    vesting_status: {vesting.get('ownership_verification_status', 'MISSING')}")
    print(f"    primary_name: {vesting.get('primary_name', '')}")
    print(f"    doc_type: {vesting.get('document_type', '')}")
    print(f"    chain events: {len(chain)}")
    print(f"    LLM final_status: {result.final_ownership_status}")
    print(f"    LLM confidence: {result.adjudication_confidence}")
    print(f"    LLM manual_review: {result.manual_review_required}")
    print(f"    LLM reason_codes: {result.reason_codes}")

print("\n=== DONE ===")
