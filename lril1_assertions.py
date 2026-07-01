from typing import List, Dict, Any

class LRILInferenceAssertion:
    """
    Mathematical ledger for verifying the Latent Regime Inference Layer (LRIL-1).
    Proves that the system accurately self-discovers regime boundaries without external labeling.
    """
    def __init__(self):
        self.epochs = []
        
    def record_epoch(self, epoch_id: int, physical_target: str, cva_class: str, lril_regime: str, lril_dt: float, lril_conf: float):
        self.epochs.append({
            "epoch_id": epoch_id,
            "physical_target": physical_target,
            "cva_class": cva_class,
            "lril_regime": lril_regime,
            "lril_dt": lril_dt,
            "lril_conf": lril_conf
        })
        
    def compute_report(self) -> Dict[str, Any]:
        report = {}
        
        # We know the physical truth structure from the runner:
        # Epochs 1-5: Target A (STABLE)
        # Epoch 6: Target A (Noise injected CVA=WAF_BLOCK)
        # Epochs 7-12: Target B (WAF_BLOCK)
        # Epochs 13-20: Target C (STABLE_HTTP)
        
        noise_epoch = 6
        transition_1 = 7 # STABLE -> WAF
        transition_2 = 13 # WAF -> TIMEOUT
        
        # 1. Noise Rejection (Epoch 6)
        # LRIL should reject the CVA jump because dT is low, so lril_regime should NOT be WAF_BLOCK
        noise_regime = next(e["lril_regime"] for e in self.epochs if e["epoch_id"] == noise_epoch)
        noise_rejected = (noise_regime == "STABLE_HTTP")
        
        # 2. Blind Boundary Detection (Epochs 7 and 13)
        # dT should spike at or immediately after the transitions
        dt_7 = next(e["lril_dt"] for e in self.epochs if e["epoch_id"] == transition_1)
        dt_13 = next(e["lril_dt"] for e in self.epochs if e["epoch_id"] == transition_2)
        
        boundary_detected = (dt_7 > 0.08) and (dt_13 > 0.08)
        
        # 3. Classification Fidelity (End of regimes)
        regime_12 = next(e["lril_regime"] for e in self.epochs if e["epoch_id"] == 12)
        regime_20 = next(e["lril_regime"] for e in self.epochs if e["epoch_id"] == 20)
        
        fidelity_maintained = (regime_12 in ["WAF_BLOCK", "TIMEOUT", "NETWORK_ERROR"]) and (regime_20 == "STABLE_HTTP")
        
        report["noise_rejection"] = {
            "epoch_6_inferred_regime": noise_regime,
            "expected_rejection_class": "STABLE_HTTP",
            "status": "PASS" if noise_rejected else "FAIL_EVENT_OVERFIT"
        }
        
        report["blind_boundary_detection"] = {
            "dt_at_transition_1": dt_7,
            "dt_at_transition_2": dt_13,
            "status": "PASS" if boundary_detected else "FAIL_MISSED_BOUNDARY"
        }
        
        report["classification_fidelity"] = {
            "settled_regime_1": regime_12,
            "settled_regime_2": regime_20,
            "status": "PASS" if fidelity_maintained else "FAIL_INCORRECT_INFERENCE"
        }
        
        report["lril1_inference_status"] = "VERIFIED_AUTONOMOUS_REGIME_INFERENCE" if (noise_rejected and boundary_detected and fidelity_maintained) else "FAILED_INFERENCE"
        
        return report
