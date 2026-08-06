from typing import Dict, Any, Optional
from cfv6_tfcm import CFV6TemporalFieldCohesionMonitor
from cfv6_dwd import CFV6DriftWindowDetector

class CFV6ExecutionCommitBoundary:
    """
    Execution Commit Boundary (ECB).
    Enforces a strict abort + full restart policy.
    No partial correctness or structurally inconsistent state is ever permitted.
    """
    def __init__(self, tfcm: CFV6TemporalFieldCohesionMonitor, dwd: CFV6DriftWindowDetector):
        self.tfcm = tfcm
        self.dwd = dwd
        
    def execute_atomic_commit(self, final_structure: str, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates the reality interface locks. 
        Either returns the fully validated extraction, or aborts entirely.
        """
        # Gate 1: Drift Window Detector
        drift_check = self.dwd.check_drift(final_structure)
        if not drift_check["stable"]:
            return {
                "committed": False,
                "data": None,
                "abort_reason": drift_check["reason"]
            }
            
        # Gate 2: Temporal Field Cohesion Monitor
        temporal_check = self.tfcm.validate_temporal_cohesion()
        if not temporal_check["valid"]:
            return {
                "committed": False,
                "data": None,
                "abort_reason": temporal_check["reason"]
            }
            
        # Gate 3: Commit Success
        return {
            "committed": True,
            "data": extracted_data,
            "abort_reason": None
        }
