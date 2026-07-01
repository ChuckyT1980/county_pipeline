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

def run_cfv4_pilot():
    print(f"--- PHASE 4A.6: CFV-4 CONTROL BASIS COMPLETION PILOT ---")
    
    hdi = HDI1Engine()
    cfv = CFV1Engine()
    classes = ["WRONG_SELECTOR", "TABLE_SHIFT", "ENTITY_BINDING_FAILURE", "NEIGHBOR_FIELD_CAPTURE"]
    epochs = 400
    
    print(f"1. Extracting FTMs from CFV-1/2 pipeline...")
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
    intervention_keys = basis["intervention_keys"]
    
    print(f"\nTarget Latent Attractor: {z2_target['mode_id']} (Eigenvalue = {z2_target['eigenvalue']:.4f})")
    
    # CLOSED LOOP SYNTHESIS
    max_iterations = 3
    for i in range(1, max_iterations + 1):
        print(f"\n--- SYNTHESIS LOOP {i} ---")
        
        # Step A: Attempt Control
        print(f"  Step A: Attempting control with {B_matrix.shape[1]} basis vectors...")
        engine = CFV3ControllabilityEngine(B_matrix, basis["P_base"], intervention_keys)
        control_result = engine.solve_control_policy(z2_target, budget=5.0, l1_lambda=0.001)
        
        u_star = np.array(list(control_result["policy"].values()))
        weight_sum = np.sum(u_star)
        print(f"          Total Intervention Weight Applied: {weight_sum:.4f}")
        
        if weight_sum > 0.1:
            print("  [SUCCESS] Z2 is now controllable. Basis spans the latent dimension.")
            break
            
        # Step B: Observe Residual
        print(f"  Step B: Observing residual (u* = 0 implies Z2 is unspanned)...")
        z_vec = np.zeros(len(classes))
        for j, (cls, val) in enumerate(z2_target["distribution"].items()):
            z_vec[j] = val
            
        residual_ext = CFV4ResidualExtractor(B_matrix)
        r_perp = residual_ext.get_orthogonal_residual(z_vec, u_star)
        
        # Step C: Extract Orthogonal Structure
        print(f"  Step C: Synthesizing missing orthogonal basis vector (b_topology)...")
        synthesis = CFV4BasisSynthesis()
        b_new = synthesis.extract_new_basis(r_perp)
        
        # Step D: Expand Basis
        print(f"  Step D: Augmenting control matrix B...")
        B_matrix = np.column_stack((B_matrix, b_new))
        new_key = f"b_topology_{i}"
        intervention_keys.append(new_key)
        
    print("\n--- FINAL CONTROL POLICY ---")
    for key, weight in zip(intervention_keys, u_star):
        print(f"  {key}: {weight:.4f}")
        
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/cfv4_report.json", "w") as f:
        json.dump({
            "final_basis_size": B_matrix.shape[1],
            "iterations": i,
            "policy": {k: float(w) for k, w in zip(intervention_keys, u_star)}
        }, f, indent=2)

if __name__ == "__main__":
    run_cfv4_pilot()
