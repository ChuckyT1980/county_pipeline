import statistics
from typing import List, Dict, Any

class CEGGeneralizationAssertion:
    """
    Mathematical ledger for verifying the Cross-Entropy Generalization Stability Test (CEG-1).
    Proves that internal system policy holds firm while mapping divergent realities.
    """
    def __init__(self):
        self.regimes = {}
        
    def record_run(self, regime_name: str, cgr1_strategies: List[str], cgr1_weights: Dict[str, float], eaf1_success: bool, cva1_class: str, vsi: float, fme: float):
        if regime_name not in self.regimes:
            self.regimes[regime_name] = {
                "cgr1_strategies": [],
                "cgr1_weights": [],
                "eaf1_success": [],
                "cva1_class": [],
                "cars2_vsi": [],
                "cars2_fme": []
            }
            
        r = self.regimes[regime_name]
        r["cgr1_strategies"].append(sorted(cgr1_strategies))
        r["cgr1_weights"].append(cgr1_weights)
        r["eaf1_success"].append(eaf1_success)
        r["cva1_class"].append(cva1_class)
        r["cars2_vsi"].append(vsi)
        r["cars2_fme"].append(fme)
        
    def compute_report(self) -> Dict[str, Any]:
        report = {}
        
        # 1. CGR-1 Structural Invariance across ALL regimes
        all_strategies = []
        all_http_weights = []
        for r_name, data in self.regimes.items():
            for s in data["cgr1_strategies"]:
                all_strategies.append(tuple(s))
            for w in data["cgr1_weights"]:
                all_http_weights.append(w.get("HTTP", 0.0))
                
        unique_strategies = len(set(all_strategies))
        report["cgr1_policy_invariance"] = {
            "unique_strategy_sets_across_regimes": unique_strategies,
            "http_weight_variance_across_regimes": statistics.variance(all_http_weights) if len(all_http_weights) > 1 else 0.0,
            "status": "PASS" if unique_strategies == 1 and (statistics.variance(all_http_weights) if len(all_http_weights) > 1 else 0.0) == 0.0 else "FAIL_POLICY_COLLAPSE"
        }
        
        # 2. EAF-1 Firewall Robustness
        all_eaf1 = []
        for data in self.regimes.values():
            all_eaf1.extend(data["eaf1_success"])
            
        report["eaf1_firewall_robustness"] = {
            "compilation_success_rate": sum(all_eaf1) / len(all_eaf1) if all_eaf1 else 0.0,
            "status": "PASS" if all(all_eaf1) else "FAIL_COMPILER_CRASH"
        }
        
        # 3. CARS-2 Distribution Stationarity (Regime separation)
        regime_metrics = {}
        for r_name, data in self.regimes.items():
            regime_metrics[r_name] = {
                "observed_classes": list(set(data["cva1_class"])),
                "mean_vsi": statistics.mean(data["cars2_vsi"]) if data["cars2_vsi"] else 0.0,
                "mean_fme": statistics.mean(data["cars2_fme"]) if data["cars2_fme"] else 0.0
            }
            
        report["cars2_distribution_stationarity"] = regime_metrics
        
        # Validate separation (e.g. timeout has high fme, stable has high vsi)
        stable_vsi = regime_metrics.get("STABLE_HTTP", {}).get("mean_vsi", 0.0)
        timeout_fme = regime_metrics.get("TIMEOUT", {}).get("mean_fme", 0.0)
        
        report["cars2_separation_validation"] = {
            "stable_regime_vsi": stable_vsi,
            "timeout_regime_fme": timeout_fme,
            "status": "PASS" if stable_vsi > 0.8 and timeout_fme > 0.8 else "FAIL_OBSERVATION_COLLAPSE"
        }
        
        # Overall CEG-1 Validation
        report["ceg1_generalization_status"] = "VERIFIED_CROSS_ENVIRONMENT_STABILITY" if all(v["status"] == "PASS" for k, v in report.items() if isinstance(v, dict) and "status" in v) else "FAILED_ENVIRONMENTAL_GENERALIZATION"
        
        return report
