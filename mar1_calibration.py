import numpy as np
from typing import List, Tuple

class MAR1AutoCalibrationEngine:
    """
    Transforms theta_1, theta_2, theta_3 into adaptive percentiles of the Pressure Outcome Distribution (POD).
    """
    def __init__(self, lambda_inertia: float = 0.05, h_min: float = 0.5, tau_min: float = 0.7):
        self.lambda_inertia = lambda_inertia
        self.h_min = h_min
        self.tau_min = tau_min
        
        # Historical percentiles
        self.theta_1 = 0.3
        self.theta_2 = 0.6
        self.theta_3 = 0.8
        
        self.pod: List[Tuple[float, str, float]] = [] # (P_t, outcome, cost)
        
    def add_observation(self, p_t: float, outcome: str, cost: float):
        """ outcome in ['success', 'partial', 'fail'] """
        self.pod.append((p_t, outcome, cost))
        # Keep window bounded (e.g., last 1000 observations)
        if len(self.pod) > 1000:
            self.pod.pop(0)
            
    def compute_adaptive_thresholds(self):
        if len(self.pod) < 10:
            return # Need more data
            
        success_p = [p for p, o, c in self.pod if o == 'success']
        partial_p = [p for p, o, c in self.pod if o in ['success', 'partial']]
        fail_p = [p for p, o, c in self.pod if o == 'fail']
        
        # Calculate instantaneous thresholds using quantiles
        if success_p:
            theta_1_star = np.percentile(success_p, 90) # p=alpha
        else:
            theta_1_star = self.theta_1
            
        if partial_p:
            theta_2_star = np.percentile(partial_p, 95) # p=beta
        else:
            theta_2_star = self.theta_2
            
        if fail_p:
            theta_3_star = np.percentile(fail_p, 50) # p=gamma
        else:
            theta_3_star = self.theta_3
            
        # Apply exponential inertia
        self.theta_1 = (1.0 - self.lambda_inertia) * self.theta_1 + self.lambda_inertia * theta_1_star
        self.theta_2 = (1.0 - self.lambda_inertia) * self.theta_2 + self.lambda_inertia * theta_2_star
        self.theta_3 = (1.0 - self.lambda_inertia) * self.theta_3 + self.lambda_inertia * theta_3_star
        
        # Ensure monotonic ladder (theta_1 < theta_2 < theta_3)
        self.theta_2 = max(self.theta_1 + 0.05, self.theta_2)
        self.theta_3 = max(self.theta_2 + 0.05, self.theta_3)
        
    def get_thresholds(self) -> Tuple[float, float, float]:
        return self.theta_1, self.theta_2, self.theta_3
