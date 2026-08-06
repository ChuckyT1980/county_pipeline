import os
import time
import json
import uuid
import random
import math
import numpy as np
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
                if "assessed_value" not in rec:
                    rec["acreage"] = 1.5
                    rec["assessed_value"] = 150000.0
                    rec["amount_due"] = 1500.0
                corpus.append(rec)
    if not corpus:
        corpus = [
            {"apn": "000-001", "acreage": 10.5, "assessed_value": 250000.0, "amount_due": 2500.0, "owner_raw": "SMITH JOHN"},
            {"apn": "000-002", "acreage": 1.2, "assessed_value": 450000.0, "amount_due": 4500.0, "owner_raw": "DOE JANE"}
        ]
    return corpus

# LAYER C - OFFLINE FEATURE MAP (φ)
def phi(X_t: dict) -> np.ndarray:
    # Extracts a 3D feature embedding [observability, value_normalized, correlation]
    obs = 1.0 if "owner_raw" in X_t else 0.5
    val_raw = X_t.get("assessed_value")
    if val_raw is None: val_raw = 150000.0
    val = min(2.0, max(0.0, val_raw / 150000.0))
    corr = 1.0
    if "assessed_value" in X_t and X_t["assessed_value"] is not None and "amount_due" in X_t and X_t["amount_due"] is not None:
        expected_due = X_t["assessed_value"] * 0.01
        actual_due = X_t["amount_due"]
        corr = min(1.0, expected_due / max(1, actual_due)) if actual_due > expected_due else min(1.0, actual_due / max(1, expected_due))
    return np.array([obs, val, corr])

# LAYER D - REGIME CENTROIDS (fixed basis)
C = [
    np.array([1.0, 1.0, 1.0]),  # 0 = Stable Basin
    np.array([0.5, 1.0, 1.0]),  # 1 = Elastic Deformation (observability drops)
    np.array([1.0, 2.0, 0.5]),  # 2 = Semantic Shear (values drift, corr breaks)
    np.array([0.0, 0.0, 0.0])   # 3 = Collapse / Absorbing State
]

def assign_regime(z_t: np.ndarray) -> int:
    dists = [np.linalg.norm(z_t - c)**2 for c in C]
    return int(np.argmin(dists))

# CONTINUOUS DRIFT OPERATOR
def D_operator(t_norm: float, X_0: dict) -> dict:
    X_t = deepcopy(X_0)
    # 1. Mean drift
    if "assessed_value" in X_t and X_t["assessed_value"] is not None:
        X_t["assessed_value"] *= (1.0 + (1.5 * t_norm)) # up to 2.5x shift
    # 2. Covariance drift
    if "amount_due" in X_t and X_t["amount_due"] is not None:
        noise = random.uniform(1.0, 1.0 + (5.0 * t_norm))
        X_t["amount_due"] *= noise # diverges from 1% rule
    # 3. Observability drift
    if "owner_raw" in X_t and random.random() < t_norm:
        del X_t["owner_raw"]
    return X_t

def build_event(timestamp: float, cycle: int, payload: dict) -> OB1Event:
    # Simulating Consistency Harness semantic fail trigger if values diverge wildly
    semantic_fail = False
    if "assessed_value" in payload and payload["assessed_value"] is not None and "amount_due" in payload and payload["amount_due"] is not None:
        expected = payload["assessed_value"] * 0.01
        actual = payload["amount_due"]
        if actual > expected * 2.0 or actual < expected * 0.5:
            semantic_fail = True
            
    pressure = 9.0 if semantic_fail else 0.5
    
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
        response_validity_flag=True,
        timeout_flag=False,
        schema_mismatch_flag=False,
        drift_detected_flag=semantic_fail,
        consistency_harness_flag=semantic_fail
    )

def kl_divergence(p, q):
    p = np.asarray(p, dtype=float) + 1e-9
    q = np.asarray(q, dtype=float) + 1e-9
    p /= p.sum()
    q /= q.sum()
    return np.sum(np.where(p != 0, p * np.log(p / q), 0))

def compute_transition_matrix(R_seq: List[int], states: int=4) -> np.ndarray:
    T = np.zeros((states, states))
    for t in range(len(R_seq)-1):
        T[R_seq[t], R_seq[t+1]] += 1
    for i in range(states):
        s = np.sum(T[i, :])
        if s > 0:
            T[i, :] /= s
        else:
            T[i, i] = 1.0
    return T

def run_h6_harness():
    print("=== Phase 4E.5 H6 Continuous Drift Harness ===")
    corpus = load_base_corpus()
    T_STEPS = 10000
    base_time = time.time()
    
    events = []
    regimes = []
    runtime = MAR1Runtime()
    
    # Generate H6 Trajectory
    for i in range(T_STEPS):
        t_norm = i / float(T_STEPS) # 0.0 to 1.0
        X_0 = random.choice(corpus)
        X_t = D_operator(t_norm, X_0)
        
        evt = build_event(base_time + (i * 0.1), i, X_t)
        events.append(evt)
        
        z_t = phi(X_t)
        r_t = assign_regime(z_t)
        regimes.append(r_t)
        
    # Execute MAR-1 sliding window stream to generate R(t) values
    r_trace = []
    for i in range(T_STEPS):
        current_time = events[i].timestamp
        window = [e for e in events[max(0, i-100):i+1] if e.timestamp >= current_time - 5.0]
        snap = Snapshot(dom={}, ob1_stream=window, wal_view=window)
        decision = runtime.execute(snap)
        r_trace.append(decision["R_t"])

    # POST-PROCESSING PIPELINE
    print("[*] Computing Transition Matrix (DRTM)...")
    DRTM = compute_transition_matrix(regimes)
    
    # Absorption pressure
    alpha_t = DRTM[0,3] + DRTM[1,3] + DRTM[2,3]
    
    # Regime churn entropy
    H_churn = 0.0
    for i in range(4):
        for j in range(4):
            if DRTM[i,j] > 0:
                H_churn -= DRTM[i,j] * math.log(DRTM[i,j])
                
    # Phase occupancies
    H_S = sum(1 for r in regimes if r == 0) / T_STEPS
    H_T = sum(1 for r in regimes if r in [1, 2]) / T_STEPS
    H_C = sum(1 for r in regimes if r == 3) / T_STEPS
    
    print(f"Phase Histogram -> STABLE: {H_S:.2f} | TRANSITIONAL: {H_T:.2f} | CRITICAL: {H_C:.2f}")
    
    # Deployability Score
    gamma = 0.5
    lmbda = 3.0
    D = (gamma * H_T) + H_C
    deployability = math.exp(-lmbda * D)
    print(f"Drift Exposure (D): {D:.4f}")
    print(f"Deployability Score: {deployability:.4f}")
    
    # Stability Envelope Check
    eps1 = 0.1
    eps2 = 1.0
    is_stable = alpha_t < eps1 and H_churn < eps2
    
    print("\n[SYSTEMIC INVARIANTS]")
    print(f"Absorption Pressure (alpha): {alpha_t:.4f} (Limit: {eps1})")
    print(f"Regime Churn Entropy (H_T): {H_churn:.4f} (Limit: {eps2})")
    print(f"Operationally Stable: {is_stable}")
    
    report = {
        "deployability": deployability,
        "histogram": {"S": H_S, "T": H_T, "C": H_C},
        "drtm": DRTM.tolist(),
        "alpha": float(alpha_t),
        "churn": float(H_churn),
        "is_stable": bool(is_stable)
    }
    
    with open("h6_resilience_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\nSaved h6_resilience_report.json")

if __name__ == "__main__":
    run_h6_harness()
