import json
import os
import numpy as np
from hdi1_engine import HDI1Engine
from cfv1_engine import CFV1Engine
from cfv1_fri import CFV1FRICalculator
from cfv2_decomposer import CFV2Decomposer
from cfv3_basis import CFV3BasisExtractor
from cfv3_controllability import CFV3ControllabilityEngine
from cfv4_residual import CFV4ResidualExtractor
from cfv4_synthesis import CFV4BasisSynthesis
from cfv5_governance import CFV5GovernanceLayer

def run_cfv5_pilot():
    print(f"--- PHASE 4A.7: CFV-5 CONTROL GOVERNANCE PILOT ---")
    
    hdi = HDI1Engine()
    cfv = CFV1Engine()
    classes = ["WRONG_SELECTOR", "TABLE_SHIFT", "ENTITY_BINDING_FAILURE", "NEIGHBOR_FIELD_CAPTURE"]
    epochs = 400
    
    print(f"1. Extracting baseline FTMs...")
    baseline_events = []
    for epoch in range(1, epochs + 1):
        event = hdi.get_next_drift_event()
        event["silent_corruption"] = True
        baseline_events.append(event)
        
    interventions = {"B": [], "C": [], "D": []}
    for base_event in baseline_events:
        for group in interventions.keys():
            resolved_type = cfv.resolve_failure(base_event["mutation_type"], group)
            int_event = base_event.copy()
            int_event["mutation_type"] = resolved_type
            interventions[group].append(int_event)
            
    calculator = CFV1FRICalculator(baseline_events)
    base_ftm = {f"{c} -> {c}": 1.0 for c in classes}
    int_ftms = {group: calculator.compute_ftm(events)["FTM"] for group, events in interventions.items()}
    
    decomposer = CFV2Decomposer(classes)
    decomp_result = decomposer.decompose(list(int_ftms.values()))
    z2_target = decomp_result["latent_modes"][1]
    
    extractor = CFV3BasisExtractor(len(classes))
    basis = extractor.extract_basis(base_ftm, int_ftms, classes)
    B_matrix = basis["B_matrix"]
    P_base = basis["P_base"]
    intervention_keys = basis["intervention_keys"]
    
    governance = CFV5GovernanceLayer(delta_min=0.1, entropy_threshold=0.5, topology_epsilon=2)
    
    print("\n[TEST] Submitting Malicious Synthetic Basis Vector to CGL-1...")
    # Create a vector that collapses APN and OWNER by shifting massive probability
    malicious_b = np.zeros_like(B_matrix[:, 0])
    malicious_b[0] = -0.9  # Remove mass from self
    malicious_b[2] = 0.9   # Dump all mass into entity binding (merging them)
    malicious_b[1] = -0.9
    malicious_b[3] = 0.9
    
    mal_val = governance.validate_basis(malicious_b, P_base)
    print(f"  Malicious Validation: {mal_val}")
    if not mal_val["accepted"]:
        print("  [SUCCESS] CGL-1 successfully blocked the semantic collapse vector!")
        
    print(f"\n--- GOVERNED SYNTHESIS LOOP ---")
    max_iterations = 3
    for i in range(1, max_iterations + 1):
        print(f"\n  Loop {i}:")
        engine = CFV3ControllabilityEngine(B_matrix, P_base, intervention_keys)
        control_result = engine.solve_control_policy(z2_target, budget=5.0, l1_lambda=0.001)
        u_star = np.array(list(control_result["policy"].values()))
        weight_sum = np.sum(u_star)
        
        if weight_sum > 0.1:
            print("  [SUCCESS] Z2 is now controllable safely.")
            break
            
        z_vec = np.zeros(len(classes))
        for j, (cls, val) in enumerate(z2_target["distribution"].items()):
            z_vec[j] = val
            
        residual_ext = CFV4ResidualExtractor(B_matrix)
        r_perp = residual_ext.get_orthogonal_residual(z_vec, u_star)
        
        synthesis = CFV4BasisSynthesis()
        b_new = synthesis.extract_new_basis(r_perp)
        
        # GATEKEEPER: Route through CFV-5 Governance
        print(f"  CGL-1 Validating Candidate b_{i}...")
        validation = governance.validate_basis(b_new, P_base)
        
        if validation["accepted"]:
            print(f"  [ACCEPTED] Basis preserves semantic invariants. Augmenting matrix.")
            B_matrix = np.column_stack((B_matrix, b_new))
            intervention_keys.append(f"b_safe_{i}")
        else:
            print(f"  [REJECTED] Basis violates semantic invariants! {validation}")
            print(f"  System is structurally limited. Cannot collapse Z2 without destroying schema.")
            break
            
    print("\n--- FINAL GOVERNED POLICY ---")
    for key, weight in zip(intervention_keys, u_star):
        print(f"  {key}: {weight:.4f}")

if __name__ == "__main__":
    run_cfv5_pilot()
