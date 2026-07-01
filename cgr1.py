from cars3_schemas import ActionConstraintVector, ExecutionMode, InstrumentDivergenceFunction
from cars2_state import VendorHealthProfile
from cars2 import EvaluationVector
from vpr2 import AcquisitionStrategy

class ConstraintGeometryResolver:
    """
    CGR-1: Constraint Geometry Resolver (formerly Constraint Solver).
    Calculates constraint viability and instrument trust weighting over partial observability manifolds.
    Never selects strategy for maximum reward; only invalidates strategies based on epistemic safety.
    """
    @staticmethod
    def resolve(
        eval_vector: EvaluationVector, 
        profile: VendorHealthProfile, 
        idf: InstrumentDivergenceFunction,
        base_acv: ActionConstraintVector = None
    ) -> ActionConstraintVector:
        
        allowed = [s.value for s in AcquisitionStrategy]
        mode = ExecutionMode.FULL
        retry_budget = 3
        diagnostic = "NORMAL"
        
        # Base authority is evenly split initially
        instrument_weights = {"HTTP": 1.0, "PLAYWRIGHT": 1.0}
        
        vsi = profile.ema_vsi
        ivd = idf.ivd
        
        # ----------------------------------------------------
        # REGION 1: LOW IVD (Instrument Agreement Region)
        # ----------------------------------------------------
        if ivd <= 0.1:
            if vsi < 0.2:
                # Extreme Systemic Inconsistency (Both agree it's fundamentally broken/unreachable)
                # Collapse all action execution.
                allowed = [AcquisitionStrategy.OBSERVATION_ONLY.value]
                mode = ExecutionMode.OBSERVATION_ONLY
                retry_budget = 0
                diagnostic = "LOW_IVD_SYSTEMIC_COLLAPSE"
                instrument_weights = {"HTTP": 0.0, "PLAYWRIGHT": 0.0}
            else:
                # Agreement on Stability (Safe Region)
                diagnostic = "LOW_IVD_AGREEMENT_SAFE"
        
        # ----------------------------------------------------
        # REGION 2: MODERATE IVD (Informational Divergence)
        # ----------------------------------------------------
        elif 0.1 < ivd <= 0.6:
            # E.g. TIMEOUT vs NONE. We do not prune strategy space, but we note the asymmetry.
            # We preserve both strategies. We mildly shift trust based on the FME delta.
            if idf.delta_fme > 0.3:
                # Playwright has higher entropy than HTTP
                instrument_weights["PLAYWRIGHT"] -= 0.3
            elif idf.delta_fme < -0.3:
                # HTTP has higher entropy than Playwright
                instrument_weights["HTTP"] -= 0.3
            diagnostic = "MODERATE_IVD_INFORMATIONAL_ASYMMETRY"
            
        # ----------------------------------------------------
        # REGION 3: HIGH IVD (Structural Divergence)
        # ----------------------------------------------------
        else: # ivd > 0.6
            # Structural divergence (e.g. WAF Block vs Full Render).
            # We explicitly adjust authority weighting and selectively prune failing instrument layers.
            if idf.delta_fme > 0.5:
                # Playwright is failing chaotically while HTTP is stable
                instrument_weights["PLAYWRIGHT"] = 0.0
                allowed = [AcquisitionStrategy.HTTP_ONLY.value, AcquisitionStrategy.OBSERVATION_ONLY.value]
                diagnostic = "HIGH_IVD_PRUNE_RENDER_LAYER"
                retry_budget = 0
            elif idf.delta_fme < -0.5:
                # HTTP is failing chaotically (or blocked) while Playwright is stable
                instrument_weights["HTTP"] = 0.0
                # HTTP strictly failing means we shouldn't use HTTP_ONLY.
                allowed = [s for s in allowed if s != AcquisitionStrategy.HTTP_ONLY.value]
                diagnostic = "HIGH_IVD_PRUNE_TRANSPORT_LAYER"
                
            else:
                # High IVD but FME delta isn't clear-cut (complex partial observability mismatch)
                instrument_weights["HTTP"] *= 0.5
                instrument_weights["PLAYWRIGHT"] *= 0.5
                mode = ExecutionMode.STRICT
                retry_budget = 0
                diagnostic = "HIGH_IVD_EPISTEMIC_CAUTION"

        return ActionConstraintVector(
            allowed_strategies=allowed,
            retry_budget=retry_budget,
            escalation_threshold=1.0 if ivd > 0.4 else 0.8,
            vendor_class_lock=profile.vendor_class,
            execution_mode=mode,
            confidence_floor=0.5 + (0.5 * ivd), # Higher IVD requires higher confidence threshold
            entropy_cap=1.0 - (0.5 * ivd), # Higher IVD lowers the acceptable entropy ceiling
            diagnostic_reason=diagnostic,
            allow_recompile=bool(ivd <= 0.6), # Block structural recompilation if we are highly uncertain about what is real
            allow_strategy_switch=True,
            allow_retry=bool(ivd <= 0.1 and vsi > 0.5), # Only allow retry in pristine low-divergence stability
            allow_actuator_fallback=False, # We never fallback. We contract space.
            instrument_authority_weights=instrument_weights
        )
