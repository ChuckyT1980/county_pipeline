import json
from cfv6_esl import CFV6EphemeralSnapshotLock
from cfv6_tfcm import CFV6TemporalFieldCohesionMonitor
from cfv6_dwd import CFV6DriftWindowDetector
from cfv6_ecb import CFV6ExecutionCommitBoundary

def run_cfv6_pilot():
    print("--- PHASE 4A.8: CFV-6 REALITY INTERFACE PILOT ---\n")
    
    # ---------------------------------------------------------
    # Scenario 1: Stable Extraction
    # ---------------------------------------------------------
    print("Scenario 1: Stable Synchronous Extraction")
    esl = CFV6EphemeralSnapshotLock()
    tfcm = CFV6TemporalFieldCohesionMonitor(sync_epsilon_ms=500)
    dwd = CFV6DriftWindowDetector(esl)
    ecb = CFV6ExecutionCommitBoundary(tfcm, dwd)
    
    # Pre-execution: Lock Snapshot
    dom_t0 = "<html><body><div id='apn'>123</div><div id='owner'>John Doe</div></body></html>"
    anchor = esl.lock_snapshot(dom_t0)
    print(f"  [ESL] Snapshot Anchor Locked: {anchor[:8]}...")
    
    # Execution: Extract fields synchronously
    tfcm.record_field_realization("APN", 100)
    tfcm.record_field_realization("OWNER", 150)
    extracted_data = {"APN": "123", "OWNER": "John Doe"}
    
    # Post-execution: Commit Boundary
    dom_tf = dom_t0 # DOM did not mutate
    result = ecb.execute_atomic_commit(dom_tf, extracted_data)
    
    print(f"  [ECB] Commit Result: {'COMMITTED' if result['committed'] else 'ABORTED'}")
    if result["abort_reason"]: print(f"  Reason: {result['abort_reason']}")
    print("-" * 50)
    
    # ---------------------------------------------------------
    # Scenario 2: Structural Drift (Mid-flight DOM Mutation)
    # ---------------------------------------------------------
    print("\nScenario 2: Mid-Flight Structural Mutation (Adversarial Drift)")
    esl = CFV6EphemeralSnapshotLock()
    tfcm = CFV6TemporalFieldCohesionMonitor(sync_epsilon_ms=500)
    dwd = CFV6DriftWindowDetector(esl)
    ecb = CFV6ExecutionCommitBoundary(tfcm, dwd)
    
    dom_t0 = "<html><body><div id='apn'>123</div><div id='owner'>John Doe</div></body></html>"
    anchor = esl.lock_snapshot(dom_t0)
    
    tfcm.record_field_realization("APN", 100)
    tfcm.record_field_realization("OWNER", 150)
    extracted_data = {"APN": "123", "OWNER": "John Doe"}
    
    # DOM mutates heavily during execution (e.g. infinite scroll loads new table)
    dom_tf = "<html><body><div id='apn'>123</div><div id='owner'>Jane Smith</div><div class='ad'>Load</div></body></html>"
    
    result = ecb.execute_atomic_commit(dom_tf, extracted_data)
    print(f"  [ECB] Commit Result: {'COMMITTED' if result['committed'] else 'ABORTED'}")
    if result["abort_reason"]: print(f"  [!] Reason: {result['abort_reason']}")
    print("-" * 50)

    # ---------------------------------------------------------
    # Scenario 3: Asynchronous Temporal Corruption
    # ---------------------------------------------------------
    print("\nScenario 3: Intra-Snapshot Asynchronous Corruption")
    esl = CFV6EphemeralSnapshotLock()
    tfcm = CFV6TemporalFieldCohesionMonitor(sync_epsilon_ms=500)
    dwd = CFV6DriftWindowDetector(esl)
    ecb = CFV6ExecutionCommitBoundary(tfcm, dwd)
    
    dom_t0 = "<html><body><div id='apn'>123</div><div id='owner'>Loading...</div></body></html>"
    anchor = esl.lock_snapshot(dom_t0)
    
    tfcm.record_field_realization("APN", 100)
    # Network lags, asynchronous JS updates the DOM much later
    tfcm.record_field_realization("OWNER", 950) 
    
    extracted_data = {"APN": "123", "OWNER": "Jane Smith"}
    
    # Structure remains identical (no new divs, just text updated)
    dom_tf = dom_t0 
    
    result = ecb.execute_atomic_commit(dom_tf, extracted_data)
    print(f"  [ECB] Commit Result: {'COMMITTED' if result['committed'] else 'ABORTED'}")
    if result["abort_reason"]: print(f"  [!] Reason: {result['abort_reason']}")
    print("-" * 50)

if __name__ == "__main__":
    run_cfv6_pilot()
