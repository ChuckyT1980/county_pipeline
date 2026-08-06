from dataclasses import dataclass

@dataclass
class MAR1State:
    observability: float      # O(t)
    latency_variance: float   # V(t)
    residual_gap: float       # G(t)
    prev_E: float
    prev_R: float

@dataclass
class MAR1Decision:
    state: str
    P: float
    E: float
    R: float

def evaluate_policy(state: MAR1State) -> MAR1Decision:
    # Elasticity: How much confidence do we have in what we're seeing?
    E_raw = 0.6 * state.observability + 0.4 * (1.0 - state.latency_variance)
    E = 0.8 * state.prev_E + 0.2 * E_raw
    E = max(0.0, min(1.0, E))
    
    # Residual Energy: How much unexplained disagreement exists?
    R_raw = state.residual_gap
    R = 0.7 * state.prev_R + 0.3 * R_raw
    R = max(0.0, min(1.0, R))
    
    # Coupling: residual amplification under low elasticity
    R_effective = R * (1.0 + 0.5 * (1.0 - E))
    
    # Pressure: where everything converges
    P = 0.5 * (1.0 - E) + 0.5 * R_effective
    P = max(0.0, min(1.0, P))
    
    # Decision Surface
    if R_effective > 0.80:
        decision_state = "SAFE_HALT"
    elif P > 0.45:
        decision_state = "SAFE_HALT"
    elif P > 0.35:
        decision_state = "PROBE_ONLY"
    elif P > 0.20:
        decision_state = "CONSERVATIVE"
    else:
        decision_state = "NORMAL"
        
    return MAR1Decision(state=decision_state, P=P, E=E, R=R)
