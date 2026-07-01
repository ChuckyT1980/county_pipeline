import json
import os
from typing import Dict, Any, List

# ============================================================
# 1. WEIGHT CONFIG (IMMUTABLE CONTRACT)
# ============================================================

WEIGHTS = {
    "drift": 0.18,
    "evolution": 0.15,
    "compatibility": 0.20,
    "replay_failure": 0.20,
    "semantic_shift": 0.15,
    "temporal_instability": 0.07,
    "query_inconsistency": 0.05,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


# ============================================================
# 2. BAND DEFINITIONS (DETERMINISTIC THRESHOLDS)
# ============================================================

def classify(score: float) -> str:
    if score >= 0.95:
        return "HEALTHY"
    elif score >= 0.85:
        return "STABLE"
    elif score >= 0.70:
        return "DEGRADED"
    elif score >= 0.50:
        return "UNSTABLE"
    return "CRITICAL"


# ============================================================
# 3. FEATURE VECTOR LOADER
# ============================================================

def load_feature_vector(run_id: str) -> Dict[str, float]:
    """
    Pulls precomputed metrics from existing system artifacts.
    No computation happens here—only aggregation.
    """

    def safe_read(path: str) -> Dict[str, Any]:
        try:
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    # Paths align with the 7-layer architecture generated artifacts
    drift = safe_read(f"replays/{run_id}/drift_report.json")
    replay = safe_read(f"replays/{run_id}/replay_result.json")
    evolution = safe_read(f"replays/{run_id}/drift_evolution_report.json")
    # Stubbing compat and sct files as those are currently static or CLI-computed
    compat = safe_read(f"replays/{run_id}/compatibility.json")
    sct = safe_read(f"replays/{run_id}/sct.json")

    return {
        # 'total_drift' from evolution or drift report
        "drift": float(evolution.get("total_drift", drift.get("total_drift", 0.0))),
        # Use sum of delta if available
        "evolution": float(sum(evolution.get("delta", [0.0]))),
        "compatibility": float(compat.get("risk_score", 0.0)),
        "replay_failure": 1.0 - float(replay.get("match_rate", 1.0)),
        "semantic_shift": float(sct.get("semantic_shift_index", 0.0)),
        "temporal_instability": float(evolution.get("instability", 0.0)),
        "query_inconsistency": float(drift.get("query_noise", 0.0)),
    }


# ============================================================
# 4. NORMALIZATION (HISTORICAL BOUNDARY SAFE)
# ============================================================

def normalize(vector: Dict[str, float], bounds: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """
    Min-max normalization using historical ledger bounds.
    """

    normalized = {}

    for k, v in vector.items():
        min_v = bounds.get(k, {}).get("min", 0.0)
        max_v = bounds.get(k, {}).get("max", 1.0)

        if max_v == min_v:
            normalized[k] = 0.0
        else:
            normalized[k] = (v - min_v) / (max_v - min_v)

    return normalized


# ============================================================
# 5. SCORING ENGINE
# ============================================================

def compute_score(vector: Dict[str, float]) -> float:
    """
    Deterministic linear projection into [0,1].
    """

    score = 1.0

    for k, weight in WEIGHTS.items():
        score -= weight * vector.get(k, 0.0)

    # hard clamp
    return max(0.0, min(1.0, score))


# ============================================================
# 6. PUBLIC API (QUERY PLANE ENTRYPOINT)
# ============================================================

def get_system_health(run_id: str, bounds: Dict[str, Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Main entry point used by QueryPlane.
    """
    if bounds is None:
        bounds = {}

    raw_vector = load_feature_vector(run_id)
    normalized_vector = normalize(raw_vector, bounds)

    score = compute_score(normalized_vector)
    status = classify(score)

    # deterministic dominant risk
    if not any(normalized_vector.values()):
        dominant_risk = "NONE"
    else:
        dominant_risk = max(normalized_vector.items(), key=lambda x: x[1])[0]

    return {
        "run_id": run_id,
        "system_health_score": round(score, 6),
        "status": status,
        "dominant_risk": dominant_risk,
        "components": normalized_vector,
    }
