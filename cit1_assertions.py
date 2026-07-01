import statistics
from typing import List, Dict, Any

class CITInvarianceAssertion:
    """
    Mathematical ledger for verifying the Closure Invariance Test (CIT-1).
    Proves that internal system recomposition generates exactly 0.0 variance.
    """
    def __init__(self):
        self.cgr1_strategies = []
        self.cgr1_weights = []
        self.eaf1_hashes = []
        self.cva1_classes = []
        self.cars2_vsi = []
        self.cars2_fme = []
        
    def record_run(self, cgr1_strategies: List[str], cgr1_weights: Dict[str, float], eaf1_hash: str, cva1_class: str, vsi: float, fme: float):
        self.cgr1_strategies.append(sorted(cgr1_strategies))
        self.cgr1_weights.append(cgr1_weights)
        self.eaf1_hashes.append(eaf1_hash)
        self.cva1_classes.append(cva1_class)
        self.cars2_vsi.append(vsi)
        self.cars2_fme.append(fme)
        
    def compute_report(self) -> Dict[str, Any]:
        report = {}
        
        # 1. System Structural Invariance (Must be 0.0 variance)
        
        # EAF-1 Hashes must be identical across all runs
        unique_hashes = len(set(self.eaf1_hashes))
        report["eaf1_structural_invariance"] = {
            "unique_hashes_seen": unique_hashes,
            "variance": 0.0 if unique_hashes == 1 else 1.0,
            "status": "PASS" if unique_hashes == 1 else "FAIL_HIDDEN_NONDETERMINISM"
        }
        
        # CGR-1 Strategies must be identical
        unique_strategies = len(set(tuple(s) for s in self.cgr1_strategies))
        report["cgr1_strategy_invariance"] = {
            "unique_sets_seen": unique_strategies,
            "variance": 0.0 if unique_strategies == 1 else 1.0,
            "status": "PASS" if unique_strategies == 1 else "FAIL_POLICY_DRIFT"
        }
        
        # CGR-1 Weights must be strictly identical
        http_weights = [w.get("HTTP", 0.0) for w in self.cgr1_weights]
        pw_weights = [w.get("PLAYWRIGHT", 0.0) for w in self.cgr1_weights]
        report["cgr1_weight_invariance"] = {
            "http_weight_variance": statistics.variance(http_weights) if len(http_weights) > 1 else 0.0,
            "playwright_weight_variance": statistics.variance(pw_weights) if len(pw_weights) > 1 else 0.0,
            "status": "PASS" if (statistics.variance(http_weights) if len(http_weights) > 1 else 0.0) == 0.0 and (statistics.variance(pw_weights) if len(pw_weights) > 1 else 0.0) == 0.0 else "FAIL_AUTHORITY_DRIFT"
        }
        
        # 2. Environmental Observational Variance (Can fluctuate naturally)
        unique_classes = set(self.cva1_classes)
        vsi_var = statistics.variance(self.cars2_vsi) if len(self.cars2_vsi) > 1 else 0.0
        fme_var = statistics.variance(self.cars2_fme) if len(self.cars2_fme) > 1 else 0.0
        
        report["environmental_observability"] = {
            "cva1_classes_observed": list(unique_classes),
            "vsi_variance": vsi_var,
            "fme_variance": fme_var,
            "status": "PASS" # Environmental variance is permitted and expected over networks
        }
        
        # Overall CIT-1 Validation
        report["cit1_closure_status"] = "VERIFIED_DETERMINISTIC_INSTRUMENT" if all(v["status"] == "PASS" for k, v in report.items() if "invariance" in k) else "FAILED_EPISTEMIC_CONTAMINATION"
        
        return report
