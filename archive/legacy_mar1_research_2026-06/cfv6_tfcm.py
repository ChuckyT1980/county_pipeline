from typing import Dict, Any

class CFV6TemporalFieldCohesionMonitor:
    """
    Temporal Field Cohesion Monitor (TFCM).
    Ensures that values materialize in a causally consistent order within the snapshot window.
    """
    def __init__(self, sync_epsilon_ms: int = 500):
        self.sync_epsilon = sync_epsilon_ms
        self.field_timestamps = {}
        
    def record_field_realization(self, field_name: str, timestamp_ms: int):
        """
        Records the exact time a field value became stable/valid in the DOM.
        """
        self.field_timestamps[field_name] = timestamp_ms
        
    def validate_temporal_cohesion(self) -> Dict[str, Any]:
        """
        Checks if |t_realize(f_i) - t_realize(f_j)| <= epsilon_sync for all extracted fields.
        """
        if not self.field_timestamps:
            return {"valid": True, "reason": "No fields recorded"}
            
        times = list(self.field_timestamps.values())
        min_time = min(times)
        max_time = max(times)
        
        drift = max_time - min_time
        
        if drift > self.sync_epsilon:
            return {
                "valid": False, 
                "drift_ms": drift,
                "reason": f"Temporal tear detected: {drift}ms exceeds epsilon {self.sync_epsilon}ms"
            }
            
        return {
            "valid": True,
            "drift_ms": drift,
            "reason": "All fields realized within synchronous cohesion window."
        }
