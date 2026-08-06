from typing import Dict, Any

class GoldenDecayTracker:
    """
    Tracks the survivorship bias of the Golden Dataset over time.
    """
    def __init__(self):
        self.counties = {}
        
    def register_county(self, county: str, initial_golden_count: int):
        self.counties[county] = {
            "active_goldens": initial_golden_count,
            "retired_goldens": 0,
            "replacement_events": 0
        }
        
    def retire_golden_parcel(self, county: str):
        if county in self.counties:
            self.counties[county]["active_goldens"] -= 1
            self.counties[county]["retired_goldens"] += 1
            
    def replace_golden_parcel(self, county: str):
        if county in self.counties:
            self.counties[county]["active_goldens"] += 1
            self.counties[county]["replacement_events"] += 1
            
    def compute_decay_metrics(self) -> Dict[str, Any]:
        metrics = {}
        for county, stats in self.counties.items():
            total_historical = stats["active_goldens"] + stats["retired_goldens"] - stats["replacement_events"]
            decay_rate = stats["retired_goldens"] / max(1, total_historical)
            metrics[county] = {
                "active_goldens": stats["active_goldens"],
                "retired_goldens": stats["retired_goldens"],
                "replacement_rate": stats["replacement_events"] / max(1, stats["active_goldens"]),
                "golden_decay_rate": decay_rate
            }
        return metrics
