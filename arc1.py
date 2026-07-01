import json
import uuid
from typing import Dict, Any
from arc1_schemas import RecompileProposal, PatchType
from sda2_schemas import StructuralDriftReport, DriftType, SuggestedAction, CVA1AnomalyEvent

class AdaptiveRecompiler:
    """
    ARC-1: Generates immutable RecompileProposals.
    Does NOT mutate disk. Purely declarative.
    """
    def __init__(self, schema_registry_path: str = "data/registry/schema_registry.json"):
        with open(schema_registry_path, "r") as f:
            self.schema_registry = json.load(f)["schemas"]
            
    def propose_recompile(self, drift_report: StructuralDriftReport, anchor_event: CVA1AnomalyEvent) -> RecompileProposal:
        vendor_class = anchor_event.vendor_class
        current_schema = self.schema_registry.get(vendor_class, {})
        
        # We need to construct the After State geometrically based on the DriftReport
        after_state = current_schema.copy()
        
        patch_type = PatchType.SELECTOR_UPDATE
        risk_score = 0.1
        
        if drift_report.drift_type == DriftType.MICRO_DRIFT:
            patch_type = PatchType.SELECTOR_UPDATE
            risk_score = 0.2
            # Simulate updating a broken selector based on the observed token layout
            # E.g., if a token moved from depth 12 to 14, we patch expected_dom_depth
            if "expected_dom_depth" in after_state:
                # In reality, this would be computed geometrically from anchor_event.dom_signature
                after_state["expected_dom_depth"] += 2 
                
        elif drift_report.drift_type == DriftType.MACRO_DRIFT:
            patch_type = PatchType.FIELD_REMAP
            risk_score = 0.5
            # We remap fields. We drop the missing anchors from our expectations.
            missing_anchors = drift_report.affected_entities
            after_state["semantic_anchors"] = [a for a in current_schema.get("semantic_anchors", []) if a not in missing_anchors]
            
        elif drift_report.drift_type == DriftType.FULL_SCHEMA_REPLACEMENT:
            patch_type = PatchType.FULL_SCHEMA_REWRITE
            risk_score = 0.9
            # Completely invalidate old anchors, adopt observed tokens from the new schema
            after_state["semantic_anchors"] = anchor_event.token_signature.get("tokens", [])[:5]
            
        return RecompileProposal(
            target_registry="schema_registry",
            vendor_class=vendor_class,
            drift_source_event_id=f"evt_{int(anchor_event.timestamp)}",
            patch_type=patch_type,
            before_state=current_schema,
            after_state=after_state,
            confidence=1.0 - risk_score,
            justification_trace=drift_report,
            risk_score=risk_score
        )
