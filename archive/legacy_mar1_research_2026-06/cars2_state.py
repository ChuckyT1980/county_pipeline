from dataclasses import dataclass
from cars2 import EvaluationVector

@dataclass
class VendorHealthProfile:
    vendor_class: str
    ema_vsi: float
    ema_fme: float
    ema_ste: float
    total_executions: int

class HealthEstimator:
    def __init__(self, alpha: float = 0.2):
        self.alpha = alpha
        self.state_db = {} # In-memory dictionary for this phase
        self.anomaly_buffer = [] # QOM-CRITICAL Anomaly Buffer
        
    def ingest(self, eval_vector: EvaluationVector, quarantine: bool = False) -> VendorHealthProfile:
        vendor = eval_vector.vendor_class
        
        if vendor not in self.state_db:
            profile = VendorHealthProfile(vendor, eval_vector.vsi_contrib, eval_vector.fme_contrib, eval_vector.ste_contrib, 1)
            self.state_db[vendor] = profile
        else:
            profile = self.state_db[vendor]
            
        if quarantine:
            # Route to Anomaly Buffer (QOM-CRITICAL). DO NOT UPDATE EMA.
            self.anomaly_buffer.append(eval_vector)
            return profile
        
        # Exponential Moving Average update
        profile.ema_vsi = (self.alpha * eval_vector.vsi_contrib) + ((1 - self.alpha) * profile.ema_vsi)
        profile.ema_fme = (self.alpha * eval_vector.fme_contrib) + ((1 - self.alpha) * profile.ema_fme)
        profile.ema_ste = (self.alpha * eval_vector.ste_contrib) + ((1 - self.alpha) * profile.ema_ste)
        profile.total_executions += 1
        
        return profile
        
    def get_profile(self, vendor_class: str) -> VendorHealthProfile:
        return self.state_db.get(vendor_class)
