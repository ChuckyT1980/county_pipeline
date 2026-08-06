import math
from dataclasses import dataclass
from typing import Dict, List, Any

@dataclass
class FailureSignature:
    stability: float
    dominant_driver: str
    classification: str
    contribution_breakdown: Dict[str, float]
    entropy: float

def profile_failure(clean_trace: List[Dict[str, Any]], fault_trace: List[Dict[str, Any]], stability: float) -> FailureSignature:
    # Stage 1: Trace Alignment & Stage 2: Delta Vectors
    delta_P, delta_E, delta_R = [], [], []
    for base, fault in zip(clean_trace, fault_trace):
        delta_P.append(abs(fault['P_t'] - base['P_t']))
        delta_E.append(abs(fault['E_t'] - base['E_t']))
        delta_R.append(abs(fault['R_t'] - base['R_t']))
        
    mean_abs_P = sum(delta_P) / max(len(delta_P), 1)
    mean_abs_E = sum(delta_E) / max(len(delta_E), 1)
    mean_abs_R = sum(delta_R) / max(len(delta_R), 1)
    
    # Stage 3: Contribution Analysis
    total = mean_abs_P + mean_abs_E + mean_abs_R
    if total == 0:
        contrib_P, contrib_E, contrib_R = 0.0, 0.0, 0.0
    else:
        contrib_P = mean_abs_P / total
        contrib_E = mean_abs_E / total
        contrib_R = mean_abs_R / total
        
    contributions = {"P": contrib_P, "E": contrib_E, "R": contrib_R}
    
    # Stage 4: Dominant Driver
    if total == 0:
        dominant_driver = "NONE"
    else:
        dominant_driver = max(contributions.keys(), key=lambda k: contributions[k])
        
    # Stage 6: Coupled Failure Detection (Entropy)
    entropy = 0.0
    if total > 0:
        for p_i in contributions.values():
            if p_i > 0:
                entropy -= p_i * math.log2(p_i)
                
    # Stage 5: Failure Geometry Classification
    classification = "UNKNOWN"
    
    if contrib_E > 0.60:
        classification = "ELASTICITY_COLLAPSE"
    elif contrib_R > 0.60:
        classification = "SEMANTIC_DRIFT_SIGNATURE"
    elif contrib_P > 0.60:
        classification = "PRESSURE_CASCADE"
    elif entropy > 1.3: # High entropy implies coupled failure
        classification = "COUPLED_FAILURE"
        
    if stability == 1.0 and total == 0:
        classification = "STABLE"

    return FailureSignature(
        stability=stability,
        dominant_driver=dominant_driver,
        classification=classification,
        contribution_breakdown={"P": round(contrib_P, 4), "E": round(contrib_E, 4), "R": round(contrib_R, 4)},
        entropy=round(entropy, 4)
    )
