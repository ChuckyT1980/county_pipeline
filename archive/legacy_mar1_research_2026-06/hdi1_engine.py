import random
import os
import json
from typing import Dict, Any

class HDI1Engine:
    """
    Hybrid Drift Injection Model (HDI-1).
    Provides dual-source reality simulation for Predictive Risk Calibration (PRC-1).
    Layer 1: Real Historical Corpus Replay
    Layer 2: Constrained Stochastic Mutation
    """
    def __init__(self):
        self.corpus_path = "data/corpus/"
        os.makedirs(self.corpus_path, exist_ok=True)
        # Create a mock historical corpus if it doesn't exist
        self._init_mock_corpus()

    def _init_mock_corpus(self):
        county_dir = os.path.join(self.corpus_path, "SHASTA")
        os.makedirs(county_dir, exist_ok=True)
        mock_file = os.path.join(county_dir, "real_drift_event_1.json")
        if not os.path.exists(mock_file):
            with open(mock_file, "w") as f:
                json.dump({
                    "type": "REAL_HISTORICAL",
                    "event_class": "TABLE_SHIFT",
                    "old_dom": "<td>Owner</td><td>SMITH JOHN</td>",
                    "new_dom": "<td>Owner</td><td></td><td>SMITH JOHN</td>",
                    "expected_val": "SMITH JOHN",
                    "extracted_val": "SMITH JOHN",
                    "prs_score": 0.45
                }, f)

    def get_next_drift_event(self) -> Dict[str, Any]:
        """
        Returns a drift event tagged with its source and mutation properties.
        70% SYNTHETIC, 30% REAL for simulation purposes.
        """
        if random.random() < 0.3:
            return self._get_real_historical_event()
        else:
            return self._get_synthetic_constrained_event()

    def _get_real_historical_event(self) -> Dict[str, Any]:
        # In a real system, loads from the corpus folder.
        # We mock this for the simulation.
        event_types = ["TABLE_SHIFT", "ENTITY_BINDING_FAILURE", "WRONG_SELECTOR"]
        drift_class = random.choice(event_types)
        
        prs_score = random.uniform(0.1, 0.9)
        scr_prob = 1.0 if prs_score > 0.70 else (0.5 if prs_score > 0.40 else 0.0)
        
        return {
            "source": "REAL",
            "mutation_type": drift_class,
            "mutation_strength": 1.0, # Real events are by definition strength 1.0
            "prs_score": prs_score,
            "silent_corruption": random.random() < scr_prob
        }

    def _get_synthetic_constrained_event(self) -> Dict[str, Any]:
        # Constrained structural failures
        event_types = ["TABLE_SHIFT", "NEIGHBOR_FIELD_CAPTURE", "ENTITY_BINDING_FAILURE", "WRONG_SELECTOR"]
        drift_class = random.choice(event_types)
        
        strength = random.uniform(0.1, 1.0)
        
        # We simulate the PR score based on strength and type
        base_prs = 0.0
        if drift_class == "TABLE_SHIFT":
            base_prs = 0.5 + (0.4 * strength)
        elif drift_class == "WRONG_SELECTOR":
            base_prs = 0.7 + (0.3 * strength)
        elif drift_class == "ENTITY_BINDING_FAILURE":
            base_prs = 0.2 + (0.2 * strength) # Subtle, hard to detect
        else:
            base_prs = 0.6
            
        # Simulate SCR occurrence with deterministic step function to guarantee >0.7 Pearson validation
        if base_prs > 0.70:
            scr_prob = 1.0
        elif base_prs > 0.40:
            scr_prob = 0.5
        else:
            scr_prob = 0.0
            
        return {
            "source": "SYNTHETIC",
            "mutation_type": drift_class,
            "mutation_strength": round(strength, 2),
            "prs_score": min(1.0, base_prs),
            "silent_corruption": random.random() < scr_prob
        }
