import json
from typing import List, Dict, Any
import math

class PRC1Analyzer:
    """
    Predictive Risk Calibration Analyzer (PRC-1).
    Computes correlation between Proposal Risk Score (PRS) and Silent Corruption Rate (SCR).
    """
    def __init__(self, ledger_data: List[Dict[str, Any]]):
        self.ledger = ledger_data
        
    def get_scr_by_prs_bucket(self) -> List[Dict[str, Any]]:
        buckets = {
            "0.0-0.2": {"attempts": 0, "scr_events": 0},
            "0.2-0.4": {"attempts": 0, "scr_events": 0},
            "0.4-0.6": {"attempts": 0, "scr_events": 0},
            "0.6-0.8": {"attempts": 0, "scr_events": 0},
            "0.8-1.0": {"attempts": 0, "scr_events": 0}
        }
        
        for event in self.ledger:
            prs = max(0.0, min(1.0, event["prs_score"]))
            scr = event["silent_corruption"]
            
            if prs <= 0.2: bucket = "0.0-0.2"
            elif prs <= 0.4: bucket = "0.2-0.4"
            elif prs <= 0.6: bucket = "0.4-0.6"
            elif prs <= 0.8: bucket = "0.6-0.8"
            else: bucket = "0.8-1.0"
            
            buckets[bucket]["attempts"] += 1
            if scr:
                buckets[bucket]["scr_events"] += 1
                
        results = []
        for bucket_name, stats in buckets.items():
            rate = stats["scr_events"] / max(1, stats["attempts"])
            results.append({
                "bucket": bucket_name,
                "attempts": stats["attempts"],
                "scr_rate": round(rate, 4)
            })
            
        return results

    def get_attribution_risk_matrix(self) -> Dict[str, float]:
        matrix = {}
        for event in self.ledger:
            if event["silent_corruption"]:
                cls = event["mutation_type"]
                prs = event["prs_score"]
                if cls not in matrix:
                    matrix[cls] = []
                matrix[cls].append(prs)
                
        avg_matrix = {}
        for cls, scores in matrix.items():
            avg_matrix[cls] = sum(scores) / len(scores)
            
        return avg_matrix

    def compute_pearson_correlation(self) -> float:
        # Simple correlation between PRS score array and SCR (0/1) array
        prs_vals = [e["prs_score"] for e in self.ledger]
        scr_vals = [1 if e["silent_corruption"] else 0 for e in self.ledger]
        
        n = len(self.ledger)
        if n == 0: return 0.0
        
        sum_x = sum(prs_vals)
        sum_y = sum(scr_vals)
        sum_x_sq = sum(x*x for x in prs_vals)
        sum_y_sq = sum(y*y for y in scr_vals)
        sum_xy = sum(x*y for x, y in zip(prs_vals, scr_vals))
        
        numerator = (n * sum_xy) - (sum_x * sum_y)
        denominator = math.sqrt((n * sum_x_sq - sum_x**2) * (n * sum_y_sq - sum_y**2))
        
        if denominator == 0: return 0.0
        return numerator / denominator
