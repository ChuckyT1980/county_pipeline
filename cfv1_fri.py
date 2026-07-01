from typing import Dict, List, Any

class CFV1FRICalculator:
    """
    Failure Redistribution Index (FRI) Calculator.
    Computes the Failure Transfer Matrix (FTM) to prove causality of interventions.
    """
    def __init__(self, baseline_events: List[Dict[str, Any]]):
        self.baseline_events = baseline_events
        # Compute base frequencies
        self.base_counts = {}
        for event in baseline_events:
            cls = event["mutation_type"]
            self.base_counts[cls] = self.base_counts.get(cls, 0) + 1
            
        total = max(1, len(baseline_events))
        self.base_probs = {k: v/total for k, v in self.base_counts.items()}

    def compute_ftm(self, intervention_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Computes Failure Transfer Matrix.
        Since we have deterministic mapping in our simulation, we can track exact transfers.
        If we didn't, we would compare macroscopic distribution deltas.
        """
        transfer_counts = {}
        # We assume intervention_events is aligned index-for-index with baseline_events
        for base_ev, int_ev in zip(self.baseline_events, intervention_events):
            base_cls = base_ev["mutation_type"]
            int_cls = int_ev["mutation_type"]
            
            if base_cls != int_cls:
                key = f"{base_cls} -> {int_cls}"
                transfer_counts[key] = transfer_counts.get(key, 0) + 1
                
        # Convert to delta probabilities
        total = max(1, len(self.baseline_events))
        ftm = {k: v/total for k, v in transfer_counts.items()}
        
        # Calculate net change per class
        int_counts = {}
        for ev in intervention_events:
            cls = ev["mutation_type"]
            int_counts[cls] = int_counts.get(cls, 0) + 1
            
        int_probs = {k: v/total for k, v in int_counts.items()}
        
        net_deltas = {}
        all_keys = set(self.base_probs.keys()).union(set(int_probs.keys()))
        for k in all_keys:
            net_deltas[k] = int_probs.get(k, 0.0) - self.base_probs.get(k, 0.0)
            
        # Calculate FRI
        # FRI = Sum of absolute positive shifts in non-targeted classes
        # This represents the total failure "mass" that was pushed into other modes
        fri = 0.0
        for delta in net_deltas.values():
            if delta > 0:
                fri += delta
                
        return {
            "FTM": ftm,
            "net_deltas": net_deltas,
            "FRI": fri
        }
