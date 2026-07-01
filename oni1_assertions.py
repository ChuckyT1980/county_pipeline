from typing import List, Dict, Any

class ONINullStateAssertion:
    """
    Mathematical ledger for verifying Observational Null-State Inference (ONI-1).
    Proves that the system distinguishes true regime drift from instrument blindness.
    """
    def __init__(self):
        self.epochs = []
        
    def record_epoch(self, epoch_id: int, physical_target: str, telemetry_dropped: bool, oni_regime: str, oni_dt: float, oni_conf: float):
        self.epochs.append({
            "epoch_id": epoch_id,
            "physical_target": physical_target,
            "telemetry_dropped": telemetry_dropped,
            "oni_regime": oni_regime,
            "oni_dt": oni_dt,
            "oni_conf": oni_conf
        })
        
    def compute_report(self) -> Dict[str, Any]:
        report = {}
        
        # Scenario:
        # Epochs 1-5: Clean STABLE
        # Epochs 6-8: Telemetry Blackout (None)
        # Epochs 9-12: Recovery into WAF_BLOCK
        
        # 1. Blindness Distinction (Epoch 6, 7, 8)
        blackout_epochs = [e for e in self.epochs if e["epoch_id"] in [6, 7, 8]]
        blind_state_achieved = all(e["oni_regime"] == "UNOBSERVED_BLIND" for e in blackout_epochs)
        zero_gradient_held = all(e["oni_dt"] == 0.0 for e in blackout_epochs)
        
        # 2. Confidence Decay (Epoch 6 -> 7 -> 8)
        conf_6 = next(e["oni_conf"] for e in blackout_epochs if e["epoch_id"] == 6)
        conf_7 = next(e["oni_conf"] for e in blackout_epochs if e["epoch_id"] == 7)
        conf_8 = next(e["oni_conf"] for e in blackout_epochs if e["epoch_id"] == 8)
        confidence_decayed = (conf_6 > conf_7 > conf_8)
        
        # 3. Post-Blackout Recovery (Epoch 12)
        recovery_regime = next(e["oni_regime"] for e in self.epochs if e["epoch_id"] == 12)
        recovery_achieved = (recovery_regime in ["WAF_BLOCK", "NETWORK_ERROR", "TIMEOUT"])
        
        report["blindness_distinction"] = {
            "unobserved_state_emitted": blind_state_achieved,
            "zero_gradient_held": zero_gradient_held,
            "status": "PASS" if (blind_state_achieved and zero_gradient_held) else "FAIL_FALSE_TRANSITION"
        }
        
        report["confidence_decay"] = {
            "conf_epoch_6": conf_6,
            "conf_epoch_8": conf_8,
            "status": "PASS" if confidence_decayed else "FAIL_EPISTEMIC_FREEZE"
        }
        
        report["recovery_resynchronization"] = {
            "settled_recovery_regime": recovery_regime,
            "status": "PASS" if recovery_achieved else "FAIL_CONTAMINATED_CAUSALITY"
        }
        
        report["oni1_null_state_status"] = "VERIFIED_NULL_STATE_INFERENCE" if (blind_state_achieved and zero_gradient_held and confidence_decayed and recovery_achieved) else "FAILED_NULL_STATE_INFERENCE"
        
        return report
