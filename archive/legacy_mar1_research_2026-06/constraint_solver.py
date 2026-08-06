from cars3_schemas import ActionConstraintVector, ExecutionMode
from cars2_state import VendorHealthProfile
from cars2 import EvaluationVector
from vpr2 import AcquisitionStrategy

class ConstraintSolver:
    """
    Pure Function Layer. No state. No history.
    Outputs the ActionConstraintVector (ACV) intersection.
    """
    @staticmethod
    def solve(eval_vector: EvaluationVector, profile: VendorHealthProfile) -> ActionConstraintVector:
        fme = profile.ema_fme
        vsi = profile.ema_vsi
        ser = eval_vector.ser
        
        # Base envelope
        allowed = [s.value for s in AcquisitionStrategy]
        mode = ExecutionMode.FULL
        retry_budget = 3
        vendor_lock = None
        diagnostic = "NORMAL"
        
        # ----------------------------------------------------
        # LEVEL 1: PREDICTABILITY (THE ENTROPY LOCK RULE)
        # ----------------------------------------------------
        if fme > 0.75:
            # High Entropy -> Total override. Unpredictability trumps capability.
            mode = ExecutionMode.STRICT
            retry_budget = 0
            allowed = [AcquisitionStrategy.HTTP_ONLY.value, AcquisitionStrategy.OBSERVATION_ONLY.value]
            diagnostic = "FME_ENTROPY_LOCK"
            
            # Fast-return because FME dominates everything. No other levels apply.
            return ActionConstraintVector(
                allowed_strategies=allowed,
                retry_budget=retry_budget,
                escalation_threshold=1.0, # Cannot escalate
                vendor_class_lock=profile.vendor_class,
                execution_mode=mode,
                confidence_floor=0.9,
                entropy_cap=0.75,
                diagnostic_reason=diagnostic
            )

        # ----------------------------------------------------
        # LEVEL 2: STABILITY (VSI BOUNDS)
        # ----------------------------------------------------
        if vsi < 0.4:
            vendor_lock = profile.vendor_class
            # Prevent escalation beyond simple state
            allowed = [s for s in allowed if s in [AcquisitionStrategy.HTTP_ONLY.value, AcquisitionStrategy.COOKIE_BOOTSTRAP.value]]
            diagnostic = "VSI_CRITICAL_DEGRADATION"
        elif 0.4 <= vsi <= 0.7:
            # Constrained escalation
            allowed = [s for s in allowed if s != AcquisitionStrategy.HYBRID_RENDER_PIPE.value]
            if diagnostic == "NORMAL": diagnostic = "VSI_MODERATE_DEGRADATION"
            
        # ----------------------------------------------------
        # LEVEL 3: EFFICIENCY (SER PRUNING)
        # ----------------------------------------------------
        if ser < 0.3:
            retry_budget = max(0, retry_budget - 2)
            if diagnostic == "NORMAL": diagnostic = "SER_EFFICIENCY_PRUNING"
            
        # ----------------------------------------------------
        # RESOLUTION & SAFE DEGRADATION LADDER (Empty Intersection)
        # ----------------------------------------------------
        if len(allowed) == 0:
            mode = ExecutionMode.OBSERVATION_ONLY
            allowed = [AcquisitionStrategy.OBSERVATION_ONLY.value]
            retry_budget = 0
            diagnostic = "CONSTRAINT_COLLAPSE"
            
        return ActionConstraintVector(
            allowed_strategies=allowed,
            retry_budget=retry_budget,
            escalation_threshold=0.8 if vsi > 0.7 else 1.0,
            vendor_class_lock=vendor_lock,
            execution_mode=mode,
            confidence_floor=0.5,
            entropy_cap=0.75,
            diagnostic_reason=diagnostic
        )
