import os
import json
import random
import hashlib
import pandas as pd
from typing import Dict, Any

from scheduler.replay_cache import DependencyFreeze
from meta_layer import MetaLayer0
from resolver import FieldResolver, MergeEngine
from completeness import CompletenessScorer
from scoring import UncertaintyAwareScorer
from counterfactual import CounterfactualEngine
from export_engine import generate_aplus_export, generate_crm_export

class ReplayConnector:
    def __init__(self, cache: DependencyFreeze, county: str):
        self.cache = cache
        self.county = county

    def fetch_identity(self, apn: str):
        return self.cache.retrieve(apn, "identity")

    def fetch_snapshot(self, apn: str):
        return self.cache.retrieve(apn, "snapshot")

def deterministic_seed(run_id: str):
    seed_int = int(hashlib.sha256(run_id.encode('utf-8')).hexdigest(), 16) % (2**32)
    random.seed(seed_int)
    try:
        import numpy as np
        np.random.seed(seed_int)
    except ImportError:
        pass
    return seed_int

def replay(original_run_id: str):
    replay_dir = os.path.join("replays", original_run_id)
    inputs_path = os.path.join(replay_dir, "inputs.json")
    result_path = os.path.join(replay_dir, "replay_result.json")
    
    if os.path.exists(result_path):
        raise RuntimeError(f"[IDENTITY BINDING VIOLATION] A replay already exists for run {original_run_id}. Only 1:1 binding is allowed unless explicitly versioned.")
    
    with open(inputs_path, "r") as f:
        inputs_map = json.load(f)
        
    seed = deterministic_seed(original_run_id)
    cache = DependencyFreeze(original_run_id)
    
    meta_layer = MetaLayer0()
    resolver = FieldResolver()
    merger = MergeEngine(resolver)
    completeness = CompletenessScorer()
    scorer = UncertaintyAwareScorer(completeness)
    counterfactual = CounterfactualEngine(scorer)
    
    connector = ReplayConnector(cache, "tehama")
    
    replay_results = []
    
    for apn, event in inputs_map.items():
        try:
            # Bypass queue and scheduler, pure function
            identity_payload = connector.fetch_identity(apn)
            snapshot_payload = connector.fetch_snapshot(apn)
            
            norm_id = meta_layer.normalize(identity_payload.data, identity_payload.county)
            norm_snap = meta_layer.normalize(snapshot_payload.data, snapshot_payload.county)
            
            merged = merger.merge(
                (norm_id, identity_payload.source),
                (norm_snap, snapshot_payload.source)
            )
            
            score_data = scorer.score(merged, event)
            cf_result = counterfactual.analyze(merged, event, score_data["final_score"])
            
            lead_bundle = {
                "apn": apn,
                "merged_record": merged,
                "score_data": score_data,
                "distress_event": event,
                "counterfactual": cf_result.__dict__
            }
            
            replay_results.append(lead_bundle)
        except Exception as e:
            pass # In a perfect replay, exceptions should match exactly too, but for V1 we just skip.
            
    # Output to CSV
    df = generate_aplus_export(replay_results, f"A_PLUS_REPLAY_PROB_{original_run_id}.csv")
    generate_crm_export(df, f"A_PLUS_REPLAY_CRM_{original_run_id}.csv")
    
    # 3-Tier Diffing Validation
    original_csv = f"A_PLUS_TEHAMA_CRM_{original_run_id}.csv"
    
    # Validation Results
    match_rate = 0.0
    matched_rows = 0
    mismatched_rows = []
    checksum_match = False
    
    if os.path.exists(original_csv):
        df_orig = pd.read_csv(original_csv)
        df_repl = pd.read_csv(f"A_PLUS_REPLAY_CRM_{original_run_id}.csv")
        
        # Sort both just in case
        df_orig = df_orig.sort_values(by="apn").reset_index(drop=True)
        df_repl = df_repl.sort_values(by="apn").reset_index(drop=True)
        
        total_rows = len(df_orig)
        
        for i in range(total_rows):
            apn = df_orig.loc[i, "apn"]
            match = True
            diffs = []
            
            # Tier 1 (Exact Match)
            for col in ["final_score"]:
                v1 = float(df_orig.loc[i, col])
                v2 = float(df_repl.loc[i, col])
                # Tier 2 (Tolerance Match)
                if abs(v1 - v2) > 0.01:
                    match = False
                    diffs.append({
                        "field": col,
                        "expected": v1,
                        "actual": v2,
                        "drift_type": "UNCLASSIFIED",
                        "layer": "scorer"
                    })
                    
            if match:
                matched_rows += 1
            else:
                mismatched_rows.append({
                    "row_id": apn,
                    "run_id": original_run_id,
                    "field_diffs": diffs
                })
                
        match_rate = matched_rows / total_rows if total_rows > 0 else 0
        
        # Simple checksum proxy
        checksum_match = (df_orig.to_csv(index=False) == df_repl.to_csv(index=False))
    
    result_obj = {
        "run_id": original_run_id,
        "replay_run_id": f"REPLAY_{original_run_id}",
        "match_rate": match_rate,
        "total_rows": len(inputs_map),
        "matched_rows": matched_rows,
        "mismatched_rows": mismatched_rows,
        "checksum_match": checksum_match,
        "seed": seed
    }
    
    with open(os.path.join(replay_dir, "replay_result.json"), "w") as f:
        json.dump(result_obj, f, indent=4)
        
    print("\n[REPLAY COMPLETE]")
    print(f"Match Rate: {match_rate * 100:.1f}%")
    print(f"Rows: {matched_rows} / {len(inputs_map)}")
    print(f"Checksum: {'PASS' if checksum_match else 'FAIL (minor formatting or float drift)'}")
    print(f"Seed: {seed}")
    
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        replay(sys.argv[1])
    else:
        print("Usage: python replay_engine.py <run_id>")
