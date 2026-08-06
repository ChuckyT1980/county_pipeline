from typing import List, Dict, Any

class IESTEcologicalAssertion:
    """
    Mathematical ledger for verifying the Integrated Ecological Stress Test (IEST-1).
    Proves that the combined CARS-2, LRIL-1, ONI-1, CGR-1, and EAF-1 layers remain coherent under chaotic stress.
    """
    def __init__(self):
        self.epochs = []
        
    def record_epoch(self, epoch_id: int, physical_target: str, telemetry_dropped: bool, 
                     cgr_http_weight: float, eaf_authorized: bool,
                     oni_regime: str, oni_dt: float, oni_conf: float):
        self.epochs.append({
            "epoch_id": epoch_id,
            "physical_target": physical_target,
            "telemetry_dropped": telemetry_dropped,
            "cgr_http_weight": cgr_http_weight,
            "eaf_authorized": eaf_authorized,
            "oni_regime": oni_regime,
            "oni_dt": oni_dt,
            "oni_conf": oni_conf
        })
        
    def compute_report(self) -> Dict[str, Any]:
        report = {}
        
        # 1. Constraint Preservation
        # authority_weight == 0.0 -> execution rejected
        # authority_weight > 0.0 -> execution allowed
        constraint_violations = 0
        for e in self.epochs:
            if e["cgr_http_weight"] == 0.0 and e["eaf_authorized"]:
                constraint_violations += 1
            if e["cgr_http_weight"] > 0.0 and not e["eaf_authorized"]:
                constraint_violations += 1
                
        report["constraint_preservation"] = {
            "violations": constraint_violations,
            "status": "PASS" if constraint_violations == 0 else "FAIL_AUTHORITY_LEAK"
        }
        
        # 2. World-Model Continuity
        # A rejected execution should not reset the ONI/LRIL state to INITIALIZING
        model_resets = 0
        for e in self.epochs:
            if not e["eaf_authorized"] and e["oni_regime"] == "INITIALIZING":
                model_resets += 1
                
        report["world_model_continuity"] = {
            "spurious_resets": model_resets,
            "status": "PASS" if model_resets == 0 else "FAIL_EPISTEMIC_AMNESIA"
        }
        
        # 3. Oscillation Detection
        # Count regime flips. If it flips back and forth constantly, it lacks hysteresis.
        regime_flips = 0
        prev_regime = None
        for e in self.epochs:
            if prev_regime is not None and e["oni_regime"] != prev_regime and e["oni_regime"] not in ["UNOBSERVED_BLIND", "AMBIGUOUS"]:
                regime_flips += 1
            if e["oni_regime"] not in ["UNOBSERVED_BLIND", "AMBIGUOUS"]:
                prev_regime = e["oni_regime"]
                
        # In a 50 epoch test with defined phases, we expect a small number of physical regime shifts (e.g. 3-5).
        # If it flips > 10 times, it is oscillating.
        report["oscillation_detection"] = {
            "total_regime_flips": regime_flips,
            "status": "PASS" if regime_flips <= 10 else "FAIL_HYSTERESIS_COLLAPSE"
        }
        
        # 4. Recovery Convergence
        # Epochs 41-50 are clean STABLE_HTTP. The system must converge to STABLE_HTTP by epoch 50.
        epoch_50 = next((e for e in self.epochs if e["epoch_id"] == 50), None)
        recovery_regime = epoch_50["oni_regime"] if epoch_50 else None
        
        report["recovery_convergence"] = {
            "final_settled_regime": recovery_regime,
            "status": "PASS" if recovery_regime == "STABLE_HTTP" else "FAIL_NON_CONVERGENT"
        }
        
        all_passed = (constraint_violations == 0 and model_resets == 0 and regime_flips <= 10 and recovery_regime == "STABLE_HTTP")
        
        report["iest1_ecological_status"] = "VERIFIED_INTEGRATED_AUTONOMY" if all_passed else "FAILED_ECOLOGICAL_COHERENCE"
        
        return report
