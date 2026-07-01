import numpy as np
from typing import Dict, Any

class MAR1MeasurementIntegrityLayer:
    """
    MIL-1: Measurement Integrity Layer
    Transforms raw signals into a Trusted Observation Tensor.
    """
    def __init__(self, probe_penalty_weight: float = 1.0):
        self.probe_penalty_weight = probe_penalty_weight
        self.signal_history = {}
        
    def execute_ground_truth_probes(self, success_rate: float) -> float:
        """
        GTPC: Ground Truth Probe Calibration.
        Returns calibration error E_probe.
        """
        # E_probe = 1 - P_probe
        return max(0.0, 1.0 - success_rate)
        
    def compute_signal_trust(self, signal_name: str, c: float, v: float, d: float, a: float) -> float:
        """
        Computes the base context-varying trust T_i(t).
        c: Consistency (0-1)
        v: Variance (0-1)
        d: Delay/staleness (0-1)
        a: Adversarial inconsistency (0-1)
        """
        # Sigmoid squash: alpha_1*C - alpha_2*V - alpha_3*D - alpha_4*A
        # Using simple linear proxy bounded to [0.1, 1.0] for the simulator
        score = c - (0.5 * v) - (0.3 * d) - (0.8 * a)
        return float(np.clip(score, 0.1, 1.0))
        
    def compute_trusted_tensor(self, 
                               raw_signals: Dict[str, float], 
                               signal_metadata: Dict[str, Dict[str, float]], 
                               probe_success_rate: float) -> Dict[str, float]:
        """
        Computes X_tilde(t) = sum( T_i'(t) * x_i(t) )
        """
        e_probe = self.execute_ground_truth_probes(probe_success_rate)
        
        trusted_tensor = {}
        for sig_name, x_i in raw_signals.items():
            meta = signal_metadata.get(sig_name, {"c": 1.0, "v": 0.0, "d": 0.0, "a": 0.0})
            t_base = self.compute_signal_trust(sig_name, meta["c"], meta["v"], meta["d"], meta["a"])
            
            # Apply GTPC penalty: T_i'(t) = T_i(t) * (1 - lambda * E_probe(t))
            t_prime = t_base * (1.0 - (self.probe_penalty_weight * e_probe))
            t_prime = max(0.01, t_prime) # Floor to prevent zero division upstream
            
            # In MAR-1, the trusted tensor is just the trust-weighted signal
            trusted_tensor[sig_name] = t_prime * x_i
            
        return trusted_tensor
