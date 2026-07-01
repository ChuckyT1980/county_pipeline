class MAR1ThresholdModelDriftDetector:
    """
    TMDD: Threshold Model Drift Detection
    Computes divergence between model self-coherence and reality coherence.
    """
    def __init__(self, epsilon: float = 1e-4):
        self.epsilon = epsilon
        
    def compute_calibration_loss(self, p_t: float, p_hat_t: float) -> float:
        """ L_cal = E[(P(t) - P_hat(t))^2] """
        return (p_t - p_hat_t) ** 2
        
    def compute_outcome_loss(self, p_t: float, theta_safe: float, failed: bool) -> float:
        """ L_real = E[ 1(failure | P(t) < theta_safe) ] """
        if failed and p_t < theta_safe:
            return 1.0
        return 0.0
        
    def compute_tmdd(self, l_cal: float, l_real: float, var_p: float) -> float:
        """
        TMDD(t) = |L_cal - L_real| / (Var(P(t)) + epsilon)
        """
        return abs(l_cal - l_real) / (var_p + self.epsilon)
