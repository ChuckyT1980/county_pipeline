from dataclasses import dataclass
from eer1_schemas import RuntimeTelemetry

@dataclass
class EvaluationVector:
    execution_graph_id: str
    county: str
    vendor_class: str
    
    efs: float          # Execution Fidelity Score
    ser: float          # Strategy Efficiency Ratio
    fme_contrib: float  # Failure Mode Entropy (instantaneous contribution)
    vsi_contrib: float  # Vendor Stability Index (instantaneous contribution)
    ste_contrib: float  # Strategy Transfer Entropy (instantaneous contribution)

class StatelessEvaluator:
    def __init__(self):
        pass
        
    def _calc_efs(self, telemetry: RuntimeTelemetry) -> float:
        """Execution Fidelity Score [0.0 - 1.0]. Did it obey VPR-3?"""
        if telemetry.strategy_planned != telemetry.strategy_observed:
            return 0.0
            
        # Hard halt verification: if there's a failure step, it must match the expected execution length logic
        # A simple model: if it failed mid-graph, it's structurally faithful, but not fully "successful".
        # Fidelity measures ADHERENCE, not success. As long as it didn't drift or hack retries.
        return 1.0 
        
    def _calc_ser(self, telemetry: RuntimeTelemetry) -> float:
        """Strategy Efficiency Ratio [0.0 - 1.0]."""
        total_steps = len(telemetry.step_results)
        if total_steps == 0: return 0.0
        
        # In a real model, we'd divide useful_steps by total_steps.
        # Here we penalize bloated executions that don't reach the target.
        if telemetry.failure_step is not None:
            # Efficiency drops if we ran many steps but still failed
            return max(0.0, 1.0 - (total_steps * 0.1))
            
        return 1.0
        
    def _calc_fme_contrib(self, telemetry: RuntimeTelemetry) -> float:
        """Instantaneous Failure Mode Entropy contribution."""
        if telemetry.failure_step is None:
            return 0.0 # Deterministic success is low entropy
            
        # Hard errors (e.g., NETWORK_ERROR, STEP_TIMEOUT) have higher entropy/randomness
        # Logic errors (e.g., WAF_BLOCK captured cleanly) are lower entropy (explainable)
        error_obj = telemetry.failure_context.get("error_type", "") if telemetry.failure_context else ""
        failure_type = error_obj.value if hasattr(error_obj, "value") else str(error_obj)
        if failure_type in ["NETWORK_ERROR", "STEP_TIMEOUT"]:
            return 1.0 # Highly random/chaotic
            
        return 0.5 # Explainable failure

    def _calc_vsi_contrib(self, telemetry: RuntimeTelemetry) -> float:
        """Instantaneous Vendor Stability Index contribution."""
        # 1.0 = stable (success), 0.0 = completely unstable (failed)
        return 1.0 if telemetry.failure_step is None else 0.0

    def _calc_ste_contrib(self, telemetry: RuntimeTelemetry) -> float:
        """Instantaneous Strategy Transfer Entropy contribution.
        High entropy (1.0) if a strategy fails unexpectedly across vendors."""
        if telemetry.failure_step is None:
            return 0.0 # Transferred successfully
        # If it failed, check if the failure is due to strategy mismatch (e.g. timeout on stateful ops)
        failure_type = telemetry.failure_context.get("error_type", "") if telemetry.failure_context else ""
        if failure_type in ["DISPATCH_MISMATCH", "STEP_TIMEOUT"]:
            return 1.0 # High transfer entropy (strategy failed to port)
        return 0.3 # Base failure entropy

    def evaluate(self, telemetry: RuntimeTelemetry, county: str, vendor_class: str) -> EvaluationVector:
        return EvaluationVector(
            execution_graph_id=telemetry.execution_graph_id,
            county=county,
            vendor_class=vendor_class,
            efs=self._calc_efs(telemetry),
            ser=self._calc_ser(telemetry),
            fme_contrib=self._calc_fme_contrib(telemetry),
            vsi_contrib=self._calc_vsi_contrib(telemetry),
            ste_contrib=self._calc_ste_contrib(telemetry)
        )
