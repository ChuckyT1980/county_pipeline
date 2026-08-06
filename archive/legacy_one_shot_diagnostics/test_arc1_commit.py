import time
from sda2_schemas import CVA1AnomalyEvent, StructuralDriftReport, DriftType, SuggestedAction
from arc1 import AdaptiveRecompiler
from arc1_schemas import StratifiedReplaySet
from arc1_shadow_mode import ARCShadowValidator
from registry_commit_gate import RegistryCommitGate

def test_arc1_and_commit_gate():
    # 1. Initialize Pipeline
    recompiler = AdaptiveRecompiler()
    commit_gate = RegistryCommitGate()
    vendor = "MPTS_HYBRID"
    
    print("--- PHASE 2.19 & 2.20 TEST: ARC-1 + COMMIT GATE ---\n")
    
    # 2. Simulate SDA-2 detecting a MICRO_DRIFT
    print(f"Step 1: Simulating SDA-2 Drift Detection for {vendor}...")
    anchor_event = CVA1AnomalyEvent(
        county_id="shasta", vendor_class=vendor, schema_id=vendor,
        failure_type="SOFT_SCHEMA_DRIFT", raw_payload_snapshot={},
        dom_signature={"layout_drift": 0.15},
        token_signature={"tokens": ["Parcel Number:", "Property Address:", "Assessed Value"]}, # Owner Name missing
        timestamp=time.time()
    )
    drift_report = StructuralDriftReport(
        drift_type=DriftType.MICRO_DRIFT, confidence=0.9, affected_entities=["Owner Name:"],
        migration_required=False, suggested_action=SuggestedAction.NONE, stability_delta=0.25, explanation="Minor drift."
    )
    
    # 3. ARC-1 Generates Proposal
    print("Step 2: ARC-1 Proposes Recompile...")
    proposal = recompiler.propose_recompile(drift_report, anchor_event)
    print(f"  -> Generated {proposal.patch_type.value} Proposal.")
    print(f"  -> Risk Score: {proposal.risk_score}")
    
    # 4. Shadow Mode Validation
    print("\nStep 3: Orchestrator runs Shadow Validation (Stratified Replay)...")
    # Mock a Stable Window of 5 successful recent traces
    stable_window = [{"trace_id": i} for i in range(5)]
    # Mock a historical drift sample
    historical_drift = CVA1AnomalyEvent(
        county_id="tehama", vendor_class=vendor, schema_id=vendor,
        failure_type="SOFT_SCHEMA_DRIFT", raw_payload_snapshot={},
        dom_signature={}, token_signature={}, timestamp=time.time() - 86400
    )
    
    replay_set = StratifiedReplaySet(anchor_event, stable_window, [historical_drift])
    is_safe = ARCShadowValidator.validate(proposal, replay_set)
    
    if not is_safe:
        print("  -> Shadow Mode rejected proposal. Halting.")
        return
        
    # 5. Commit Gate Atomic Write
    print("\nStep 4: Commit Authority Layer Applies Patch...")
    version_id = commit_gate.commit(proposal)
    print(f"  -> Success! Committed as Version: {version_id}")
    
    # 6. Test Rollback
    print("\nStep 5: Simulating Administrator Rollback...")
    success = commit_gate.rollback(proposal.target_registry, version_id)
    print(f"  -> Rollback Success? {success}")

if __name__ == "__main__":
    test_arc1_and_commit_gate()
