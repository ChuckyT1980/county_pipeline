from typing import Optional
from lril1 import LatentRegimeInferenceLayer, InferredRegimeState

class NullStateInferenceEngine(LatentRegimeInferenceLayer):
    """
    ONI-1: Observational Null-State Inference Engine.
    Extends LRIL-1 to explicitly model instrument blindness.
    Rule: If no observation -> Freeze ontology (VSI/FME), degrade epistemology (confidence).
    """
    def __init__(self, velocity_threshold: float = 0.08, decay_lambda: float = 0.5):
        super().__init__(velocity_threshold)
        self.decay_lambda = decay_lambda
        self.last_known_regime: str = "INITIALIZING"
        
    def infer_with_null_handling(self, 
                                 current_vsi: Optional[float], 
                                 current_fme: Optional[float], 
                                 current_cva_class: Optional[str]) -> InferredRegimeState:
        
        # 1. Null-State Intercept
        if current_cva_class is None:
            # We are blind. Ontology is frozen (we don't update prev_vsi or prev_fme).
            # Epistemology degrades exponentially.
            self.confidence = self.confidence * self.decay_lambda
            self.current_regime = "UNOBSERVED_BLIND"
            
            # Gradient is strictly 0.0 during silence (no hallucinated transitions)
            return InferredRegimeState(self.current_regime, 0.0, self.confidence, False)
            
        # 2. Recovery / Resynchronization Intercept
        if self.current_regime == "UNOBSERVED_BLIND":
            # We were blind, but observation has returned.
            # We must resynchronize. If the CVA class matches our last known regime, 
            # we just resume. If it's different, we are emerging into a new regime.
            self.current_regime = self.last_known_regime # Restore last known belief temporarily to compute drift
            # Let the standard LRIL-1 logic process the jump between the frozen state and the new observation.
            
        # 3. Standard LRIL-1 Execution
        inferred_state = super().infer(current_vsi, current_fme, current_cva_class)
        
        # Keep track of the last known physical regime
        if inferred_state.regime_label != "UNOBSERVED_BLIND":
            self.last_known_regime = inferred_state.regime_label
            
        return inferred_state
