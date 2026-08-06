import json
from typing import Dict, Any, Optional

class SCRClassificationEvent:
    def __init__(self, classification: str, confidence: float, evidence_type: str, selector_delta: str, dom_delta_score: str, prs_score: float, county: str, field: str):
        self.classification = classification
        self.confidence = confidence
        self.evidence_type = evidence_type
        self.selector_delta = selector_delta
        self.dom_delta_score = dom_delta_score
        self.prs_score = prs_score
        self.county = county
        self.field = field

    def to_dict(self):
        return {
            "classification": self.classification,
            "confidence": self.confidence,
            "evidence_type": self.evidence_type,
            "selector_delta": self.selector_delta,
            "dom_delta_score": self.dom_delta_score,
            "prs_score": self.prs_score,
            "county": self.county,
            "field": self.field
        }

class SCA1Classifier:
    """
    Silent Corruption Attribution Layer (SCA-1).
    Classifies Silent Corruption Rate (SCR) events into targetable buckets using a Hierarchical Attribution Model.
    """
    def __init__(self):
        pass

    def _tier1_structural_analysis(self, expected_selector: str, proposed_selector: str, old_dom: Optional[str], new_dom: Optional[str]) -> Optional[Dict[str, Any]]:
        # Simulate DOM diffing
        if not old_dom or not new_dom:
            return None # Missing DOM snapshot, fallback to Tier 2
            
        # Example heuristic logic:
        # If expected selector was td[4] and proposed is td[5], it's a TABLE_SHIFT
        if "td[" in expected_selector and "td[" in proposed_selector:
            return {"classification": "TABLE_SHIFT", "confidence": 0.94, "evidence_type": "STRUCTURAL", "dom_delta_score": "High-Shift"}
            
        # If selector structurally shifted only slightly but captures completely wrong entity context
        if proposed_selector.startswith("div.parcel") and expected_selector.startswith("div.parcel"):
            if "adjacent" in new_dom.lower():
                return {"classification": "ENTITY_BINDING_FAILURE", "confidence": 0.88, "evidence_type": "STRUCTURAL", "dom_delta_score": "Entity-Boundary-Shift"}
                
        return None

    def _tier2_semantic_analysis(self, expected_val: str, extracted_val: str, field_type: str) -> Dict[str, Any]:
        # Fallback heuristic semantic analysis
        if field_type == "APN" and any(c.isalpha() for c in extracted_val):
            # We expected an APN format (e.g. 123-456), but got alpha characters (e.g. "John Smith")
            return {"classification": "NEIGHBOR_FIELD_CAPTURE", "confidence": 0.75, "evidence_type": "SEMANTIC"}
            
        if field_type == "OWNER" and "$" in extracted_val:
            return {"classification": "WRONG_SELECTOR", "confidence": 0.82, "evidence_type": "SEMANTIC"}
            
        return {"classification": "UNKNOWN", "confidence": 0.30, "evidence_type": "SEMANTIC"}

    def classify(self, field: str, expected_val: str, extracted_val: str, expected_selector: str, proposed_selector: str, 
                 old_dom: Optional[str], new_dom: Optional[str], prs_score: float, county: str) -> SCRClassificationEvent:
        
        # Tier 1: Structural Attribution
        structural_result = self._tier1_structural_analysis(expected_selector, proposed_selector, old_dom, new_dom)
        
        if structural_result:
            classification = structural_result["classification"]
            confidence = structural_result["confidence"]
            evidence_type = structural_result["evidence_type"]
            dom_delta = structural_result.get("dom_delta_score", "None")
        else:
            # Tier 2: Semantic Attribution
            semantic_result = self._tier2_semantic_analysis(expected_val, extracted_val, field)
            classification = semantic_result["classification"]
            confidence = semantic_result["confidence"]
            evidence_type = semantic_result["evidence_type"]
            dom_delta = "Not Computed"
            
        selector_delta = f"{expected_selector} -> {proposed_selector}"
        
        return SCRClassificationEvent(
            classification=classification,
            confidence=confidence,
            evidence_type=evidence_type,
            selector_delta=selector_delta,
            dom_delta_score=dom_delta,
            prs_score=prs_score,
            county=county,
            field=field
        )
