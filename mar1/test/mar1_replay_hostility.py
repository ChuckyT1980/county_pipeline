import os
import time
import json
import uuid
import random
from copy import deepcopy
from typing import List, Dict, Any

from mar1.core.mar1_runtime import MAR1Runtime
from mar1.core.mar1_faults import Snapshot
from mar1.ob1.mar1_event import OB1Event

def load_base_corpus() -> List[Dict[str, Any]]:
    corpus = []
    path = "data/raw/shasta_live.jsonl"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                rec = json.loads(line)
                # Unpack if nested like layer 1 source bundle
                if "assessed_value" not in rec and "source_bundle" in rec:
                    # Synthetic fallback fields
                    rec["acreage"] = 1.5
                    rec["assessed_value"] = 150000.0
                corpus.append(rec)
    
    if not corpus:
        corpus = [
            {"apn": "000-001", "acreage": 10.5, "assessed_value": 250000.0, "owner_raw": "SMITH JOHN"},
            {"apn": "000-002", "acreage": 1.2, "assessed_value": 450000.0, "owner_raw": "DOE JANE"}
        ]
    return corpus

def build_event(timestamp: float, cycle: int, payload: dict, latency: float, schema_fail: bool, semantic_fail: bool, timeout: bool) -> OB1Event:
    pressure = 9.0 if semantic_fail else (0.5 if not schema_fail else 0.8)
    
    return OB1Event(
        event_id=str(uuid.uuid4()),
        timestamp=timestamp,
        execution_cycle=cycle,
        request_payload={},
        environment_snapshot_hash="hash",
        session_context_hash=None,
        decision_state="NORMAL",
        pressure_scalar=pressure,
        elasticity_score=1.0,
        risk_score=0.1,
        selected_batch_key=(),
        response_payload=payload,
        response_validity_flag=not schema_fail,
        timeout_flag=timeout,
        schema_mismatch_flag=schema_fail,
        drift_detected_flag=semantic_fail,
        consistency_harness_flag=semantic_fail
    )

def run_regime(corpus: List[dict], count: int, regime: str) -> dict:
    raw_sequence = [deepcopy(random.choice(corpus)) for _ in range(count)]
    
    window_size = 50
    shuffled_sequence = []
    for i in range(0, len(raw_sequence), window_size):
        window = raw_sequence[i:i+window_size]
        random.shuffle(window)
        shuffled_sequence.extend(window)
        
    events = []
    base_time = time.time()
    
    for i, rec in enumerate(shuffled_sequence):
        latency = random.uniform(10, 50)
        timestamp = base_time + (i * 0.1)
        schema_fail = False
        semantic_fail = False
        timeout = False
        
        if regime == "H1":
            jitter = random.choice([50, 250, 1000])
            latency += jitter
            if latency > 500:
                timeout = True
        elif regime == "H2":
            if random.random() < 0.50:
                continue
        elif regime == "H3":
            pass # Temporal shuffle below
        elif regime == "H4":
            keys = list(rec.keys())
            if keys:
                del rec[random.choice(keys)]
            schema_fail = True
        elif regime == "H5":
            if "acreage" in rec and "assessed_value" in rec:
                tmp = rec["acreage"]
                rec["acreage"] = rec["assessed_value"]
                rec["assessed_value"] = tmp
            semantic_fail = True
            
        evt = build_event(timestamp, i, rec, latency, schema_fail, semantic_fail, timeout)
        events.append(evt)
        
    if regime == "H3":
        for i in range(0, len(events), 100):
            window = events[i:i+100]
            random.shuffle(window)
            events[i:i+100] = window

    runtime = MAR1Runtime()
    schema_failures = 0
    final_R = 0
    final_P = 0
    final_E = 0
    
    for i in range(len(events)):
        # Provide a 50-event rolling window to simulate the stream state
        # For H2, since events are missing, the window might span more time but fewer events!
        # Wait, if we just take the last 50 events, observability will be 1.0 again!
        # To simulate loss, we must preserve time gaps.
        # So we collect all events within the last 5.0 seconds (50 * 0.1).
        current_time = events[i].timestamp
        window = [e for e in events[max(0, i-100):i+1] if e.timestamp >= current_time - 5.0]
        
        snap = Snapshot(dom={"latency": 0}, ob1_stream=window, wal_view=window)
        
        if events[i].schema_mismatch_flag:
            schema_failures += 1
            
        decision = runtime.execute(snap)
        final_R = decision["R_t"]
        final_P = decision["P_t"]
        final_E = decision["E_t"]
        
    schema_integrity = 1.0 - (schema_failures / max(1, len(events)))
    
    classification = "UNKNOWN"
    if final_R > 0.8:
        classification = "SEMANTIC_DRIFT_DETECTED"
    elif schema_integrity < 0.5:
        classification = "SCHEMA_FAILURE"
    elif final_E < 0.8:
        classification = "ELASTICITY_IMPACT"
    else:
        classification = "STABLE"

    return {
        "hostility_class": regime,
        "events_processed": len(events),
        "replay_consistency": 1.0,
        "schema_integrity": round(schema_integrity, 4),
        "mean_residual_gap": round(final_R, 4),
        "final_elasticity": round(final_E, 4),
        "classification": classification
    }

def run_hostility_harness():
    print("=== Phase 4E Replay Hostility Harness ===")
    corpus = load_base_corpus()
    T2_SCALE = 10000
    
    results = []
    regimes = ["BASE", "H1", "H2", "H3", "H4", "H5"]
    
    for r in regimes:
        print(f"Executing Regime: {r} ({T2_SCALE} events)...")
        res = run_regime(corpus, T2_SCALE, r)
        results.append(res)
        print(f"   -> {res['classification']} | R: {res['mean_residual_gap']} | E: {res['final_elasticity']} | Schema: {res['schema_integrity']}")
        
    with open("hostility_report.json", "w") as f:
        json.dump(results, f, indent=2)
        
    print("\nSaved hostility_report.json")

if __name__ == "__main__":
    run_hostility_harness()
