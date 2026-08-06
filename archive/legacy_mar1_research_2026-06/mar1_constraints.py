from typing import Dict

class MAR1GlobalConstraintMonitor:
    """
    Computes the unified scalar decision pressure P(t).
    """
    def __init__(self, w1: float = 1.0, w2: float = 1.0, w3: float = 1.0, w4: float = 1.0, w5: float = 1.0):
        self.w1 = w1
        self.w2 = w2
        self.w3 = w3
        self.w4 = w4
        self.w5 = w5
        
        self.prev_elasticity = 1.0
        
    def compute_pressure(self, trusted_metrics: Dict[str, float]) -> float:
        """
        Calculates P(t) = w1*(1 - E(t)) + w2*SCR(t) + w3*||G(t)|| + w4*|E(t) - E(t-1)| + w5*R_ERM(t)
        Requires trusted metrics from MIL-1.
        """
        e_t = trusted_metrics.get("E", 1.0)
        scr_t = trusted_metrics.get("SCR", 0.0)
        g_t_norm = trusted_metrics.get("G_norm", 0.0)
        r_erm_t = trusted_metrics.get("R_ERM", 0.0)
        
        delta_e = abs(e_t - self.prev_elasticity)
        
        p_t = (
            self.w1 * (1.0 - e_t) +
            self.w2 * scr_t +
            self.w3 * g_t_norm +
            self.w4 * delta_e +
            self.w5 * r_erm_t
        )
        
        self.prev_elasticity = e_t
        return p_t
