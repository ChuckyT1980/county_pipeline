from typing import Dict, Any
from prc1_analyzer import PRC1Analyzer

class PRC1Assertion:
    """
    Mathematical ledger to assert PRC-1 Graduation Gates.
    """
    def __init__(self, analyzer: PRC1Analyzer):
        self.analyzer = analyzer

    def compute_report(self) -> Dict[str, Any]:
        report = {}
        
        # 1. Total Events Assertion (>100)
        total_events = len(self.analyzer.ledger)
        report["event_volume"] = {
            "total": total_events,
            "status": "PASS" if total_events >= 100 else "FAIL_INSUFFICIENT_DATA"
        }
        
        # 2. Pearson Correlation Assertion (>0.7)
        pearson = self.analyzer.compute_pearson_correlation()
        report["predictive_correlation"] = {
            "pearson_coefficient": round(pearson, 3),
            "status": "PASS" if pearson > 0.7 else "FAIL_NOISE"
        }
        
        # 3. Top 3 Dominant SCR Classes
        matrix = self.analyzer.get_attribution_risk_matrix()
        # sort by volume (which we need to compute)
        volumes = {}
        for event in self.analyzer.ledger:
            if event["silent_corruption"]:
                cls = event["mutation_type"]
                volumes[cls] = volumes.get(cls, 0) + 1
                
        sorted_classes = sorted(volumes.items(), key=lambda x: x[1], reverse=True)
        top_3 = [c[0] for c in sorted_classes[:3]]
        
        report["dominant_failure_modes"] = {
            "top_3": top_3,
            "distribution": volumes,
            "status": "PASS" if len(top_3) >= 1 else "FAIL_NO_FAILURES_FOUND"
        }
        
        all_passed = (report["event_volume"]["status"] == "PASS" and 
                      report["predictive_correlation"]["status"] == "PASS" and
                      report["dominant_failure_modes"]["status"] == "PASS")
                      
        report["prc1_calibration_status"] = "VERIFIED_PREDICTIVE_CALIBRATION" if all_passed else "FAILED_CALIBRATION"
        
        return report
