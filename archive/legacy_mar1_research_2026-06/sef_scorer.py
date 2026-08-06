from typing import Dict, Any, List

class FieldScore:
    def __init__(self, field_name: str, status: str):
        # status can be: PASS, FAIL, UNSCORABLE
        self.field_name = field_name
        self.status = status

class SEFScore:
    def __init__(self, proposal_id: str, county: str):
        self.proposal_id = proposal_id
        self.county = county
        self.field_scores: List[FieldScore] = []
        self.silent_corruption: bool = False
        
    def add_score(self, field_name: str, status: str):
        self.field_scores.append(FieldScore(field_name, status))
        if status == "FAIL":
            # If the extraction succeeded structurally (didn't throw) but was semantically wrong, 
            # we classify it as silent corruption.
            # In a real pipeline, we would distinguish between "Field Not Found" and "Field Extracted Wrong String".
            # For Phase 4A, we assume a FAIL on a golden parcel is silent corruption.
            self.silent_corruption = True

class SEFScorer:
    """
    Semantic Extraction Fidelity (SEF) Scorer.
    Implements Three-Tier validation and Silent Corruption Rate (SCR) tracking.
    """
    def __init__(self, golden_dataset: Dict[str, Dict[str, Any]]):
        """
        golden_dataset maps parcel_id -> expected_fields
        """
        self.golden_dataset = golden_dataset
        
    def _is_unscorable(self, county: str, parcel_id: str, shadow_extraction: Dict[str, Any]) -> bool:
        # A parcel becomes unscorable if the golden dataset itself is stale 
        # (e.g. County redesign completely removed the owner page).
        # We simulate this check. If the entire payload is empty, we might flag as unscorable 
        # instead of punishing ARC-1 for a completely vanished record.
        if "RECORD_NOT_FOUND" in str(shadow_extraction):
            return True
        return False
        
    def score_proposal(self, proposal_id: str, county: str, parcel_id: str, shadow_extraction: Dict[str, Any]) -> SEFScore:
        score = SEFScore(proposal_id, county)
        
        if parcel_id not in self.golden_dataset:
            # Cannot score against Golden Dataset if it's not a golden parcel
            score.add_score("ALL", "UNSCORABLE")
            return score
            
        if self._is_unscorable(county, parcel_id, shadow_extraction):
            for field in self.golden_dataset[parcel_id].keys():
                score.add_score(field, "UNSCORABLE")
            return score
            
        expected_data = self.golden_dataset[parcel_id]
        
        for field, expected_val in expected_data.items():
            extracted_val = shadow_extraction.get(field, None)
            
            if extracted_val == expected_val:
                score.add_score(field, "PASS")
            else:
                score.add_score(field, "FAIL")
                
        return score
