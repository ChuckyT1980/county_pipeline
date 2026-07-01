from typing import List, Dict, Any

class RBDBoundaryDriftAssertion:
    """
    Mathematical ledger for verifying the Regime Boundary Drift Stability Test (RBD-1).
    Proves that the system maintains a stable latent model under shifting world states (Hysteresis & Continuity).
    """
    def __init__(self, alpha: float):
        self.alpha = alpha
        self.epochs = []
        
    def record_epoch(self, epoch_id: int, target_url: str, cva_class: str, vsi: float, fme: float, http_weight: float, eaf1_success: bool):
        self.epochs.append({
            "epoch_id": epoch_id,
            "target_url": target_url,
            "cva_class": cva_class,
            "cars2_vsi": vsi,
            "cars2_fme": fme,
            "cgr1_http_weight": http_weight,
            "eaf1_success": eaf1_success
        })
        
    def compute_report(self) -> Dict[str, Any]:
        report = {}
        
        vsi_deltas = []
        fme_deltas = []
        weight_deltas = []
        
        for i in range(1, len(self.epochs)):
            prev = self.epochs[i-1]
            curr = self.epochs[i]
            
            vsi_deltas.append(abs(curr["cars2_vsi"] - prev["cars2_vsi"]))
            fme_deltas.append(abs(curr["cars2_fme"] - prev["cars2_fme"]))
            weight_deltas.append(abs(curr["cgr1_http_weight"] - prev["cgr1_http_weight"]))
            
        # Max theoretical jump under EMA is alpha (if transitioning from 1 to 0 or 0 to 1)
        max_allowed_jump = self.alpha + 0.05 # Add small epsilon for floating point / CGR non-linear mapping
        
        # 1. CARS-2 Continuity
        vsi_continuous = all(d <= max_allowed_jump for d in vsi_deltas)
        fme_continuous = all(d <= max_allowed_jump for d in fme_deltas)
        
        # 2. CGR-1 Hysteresis Stability
        # Weight should also not jump violently. CGR maps VSI directly, so delta should be bounded.
        weight_stable = all(d <= max_allowed_jump for d in weight_deltas)
        
        # 3. EAF-1 Non-Retraction
        eaf1_success = all(e["eaf1_success"] for e in self.epochs)
        
        report["cars2_continuity"] = {
            "max_vsi_jump_observed": max(vsi_deltas) if vsi_deltas else 0.0,
            "max_fme_jump_observed": max(fme_deltas) if fme_deltas else 0.0,
            "theoretical_max_jump": self.alpha,
            "status": "PASS" if vsi_continuous and fme_continuous else "FAIL_FRAGMENTATION"
        }
        
        report["cgr1_hysteresis_stability"] = {
            "max_weight_jump_observed": max(weight_deltas) if weight_deltas else 0.0,
            "status": "PASS" if weight_stable else "FAIL_POLICY_OSCILLATION"
        }
        
        report["eaf1_non_retraction"] = {
            "status": "PASS" if eaf1_success else "FAIL_FIREWALL_RETRACTION"
        }
        
        report["rbd1_drift_status"] = "VERIFIED_REGIME_TRANSITION_INVARIANCE" if (vsi_continuous and fme_continuous and weight_stable and eaf1_success) else "FAILED_STABILITY_UNDER_DRIFT"
        
        return report
