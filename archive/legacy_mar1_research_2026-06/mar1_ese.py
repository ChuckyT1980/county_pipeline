import math
from typing import Tuple

class MAR1EpistemicStabilityEnvelope:
    """
    ESE: Epistemic Stability Envelope
    Unifies MIL-1 and TMDD to classify and dampen epistemic collapse.
    """
    def __init__(self, alpha: float = 2.0):
        self.alpha = alpha
        self.prev_mil_volatility = 0.0
        self.prev_tmdd_volatility = 0.0
        
    def compute_ese(self, mil_trust: float, tmdd_score: float) -> float:
        """
        Computes ESE(t) = exp(-alpha * D(t)) where D(t) = |MIL(t) - TMDD(t)|.
        Assuming MIL and TMDD are normalized [0,1] for comparison.
        (MIL trust is high when healthy, TMDD is low when healthy, so D(t) uses inverted TMDD for agreement check)
        Actually, MIL trust = 1.0 (good), TMDD = 0.0 (good).
        So they "agree" if MIL is 1.0 and (1-TMDD) is 1.0.
        D(t) = |MIL_trust - (1.0 - TMDD)|
        """
        # Ensure TMDD is clamped [0, 1] for this calculation
        norm_tmdd = min(max(tmdd_score, 0.0), 1.0)
        d_t = abs(mil_trust - (1.0 - norm_tmdd))
        
        ese = math.exp(-self.alpha * d_t)
        return ese
        
    def classify_collapse(self, 
                          mil_volatility: float, 
                          tmdd_volatility: float, 
                          directional_coherence_k: float, 
                          monotonic_drift_m: float) -> str:
        """
        Classifies the shape of an ESE collapse using second-order derivatives.
        Returns: ADVERSARIAL_ATTACK, MODEL_INSTABILITY, SENSOR_CORRUPTION, or COUPLED_FAILURE
        """
        # 1. TRUE ADVERSARIAL ATTACK
        if directional_coherence_k > 0.6 and monotonic_drift_m > 0 and mil_volatility >= (0.8 * tmdd_volatility):
            return "ADVERSARIAL_ATTACK"
            
        # 2. MODEL INSTABILITY (False trigger)
        if directional_coherence_k <= 0.1 and tmdd_volatility > (1.5 * mil_volatility):
            return "MODEL_INSTABILITY"
            
        # 3. SENSOR CORRUPTION
        if mil_volatility > (1.5 * tmdd_volatility) and abs(directional_coherence_k) < 0.3:
            return "SENSOR_CORRUPTION"
            
        # 4. COUPLED FAILURE
        return "COUPLED_FAILURE"
        
    def apply_dampening(self, p_t: float, ese_t: float) -> float:
        """
        P'(t) = P(t) / (ESE(t) + epsilon)
        As ESE -> 0 (high disagreement), P'(t) -> infinity (forcing SAFE HALT)
        """
        return p_t / max(ese_t, 0.01)
