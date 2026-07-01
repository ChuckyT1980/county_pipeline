import json
from sda2_schemas import CVA1AnomalyEvent, StructuralDriftReport, DriftType, SuggestedAction

class StructuralDriftMapper:
    """
    SDA-2: Version Control System for Reality.
    Geometric Change Detector over Structured Reality.
    """
    def __init__(self, registry_path: str = "data/registry/schema_registry.json"):
        with open(registry_path, "r") as f:
            self.registry = json.load(f)["schemas"]
            
    def map_drift(self, event: CVA1AnomalyEvent) -> StructuralDriftReport:
        baseline = self.registry.get(event.schema_id)
        if not baseline:
            return StructuralDriftReport(
                drift_type=DriftType.FULL_SCHEMA_REPLACEMENT,
                confidence=1.0,
                affected_entities=["unknown_schema"],
                migration_required=True,
                suggested_action=SuggestedAction.REBUILD_VPR_DOMAIN_MODEL,
                stability_delta=1.0,
                explanation=f"Schema ID {event.schema_id} entirely missing from registry."
            )
            
        # Extract observations
        observed_tokens = event.token_signature.get("tokens", [])
        
        # 1. Semantic Anchor Stability
        expected_anchors = baseline.get("semantic_anchors", [])
        missing_anchors = [a for a in expected_anchors if a not in observed_tokens]
        anchor_loss_ratio = len(missing_anchors) / len(expected_anchors) if expected_anchors else 0
        
        # 2. DOM Distance / Layout Drift (mocked proxy logic)
        # In a real environment, we'd hash the DOM tree structure or use Edit Distance.
        # For this prototype, we simulate layout drift from the anomaly event signature.
        layout_drift_score = event.dom_signature.get("layout_drift", 0.0)
        
        # Classification Logic
        drift_type = DriftType.NO_DRIFT
        action = SuggestedAction.NONE
        migration = False
        
        if anchor_loss_ratio > 0.7 or layout_drift_score > 0.8:
            drift_type = DriftType.FULL_SCHEMA_REPLACEMENT
            action = SuggestedAction.RE_FINGERPRINT_SDA1
            migration = True
            explanation = f"Structural inversion. {anchor_loss_ratio*100:.0f}% of semantic anchors lost."
            
        elif anchor_loss_ratio > 0.2 or layout_drift_score > 0.4:
            drift_type = DriftType.MACRO_DRIFT
            action = SuggestedAction.UPDATE_SCDA_MAPPING
            migration = True
            explanation = f"Partial schema restructuring. Layout drift: {layout_drift_score:.2f}."
            
        elif anchor_loss_ratio > 0.0 or layout_drift_score > 0.1:
            drift_type = DriftType.MICRO_DRIFT
            action = SuggestedAction.NONE
            explanation = "Minor structural variance or optional fields added."
        else:
            explanation = "DOM geometrically matches baseline. Discrepancy likely network artifact."
            
        return StructuralDriftReport(
            drift_type=drift_type,
            confidence=0.9,
            affected_entities=missing_anchors,
            migration_required=migration,
            suggested_action=action,
            stability_delta=anchor_loss_ratio,
            explanation=explanation
        )
