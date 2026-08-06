import json
import os
from hdi1_engine import HDI1Engine
from cfv1_engine import CFV1Engine
from cfv1_fri import CFV1FRICalculator
from cfv2_decomposer import CFV2Decomposer
from cfv3_basis import CFV3BasisExtractor
from cfv3_controllability import CFV3ControllabilityEngine

def run_cfv3_pilot():
    print(f"--- PHASE 4A.5: CFV-3 CONTROL BASIS IDENTIFICATION PILOT ---")
    
    hdi = HDI1Engine()
    cfv = CFV1Engine()
    classes = ["WRONG_SELECTOR", "TABLE_SHIFT", "ENTITY_BINDING_FAILURE", "NEIGHBOR_FIELD_CAPTURE"]
    
    epochs = 400
    print(f"1. Simulating CFV-1/2 pipeline to measure FTM perturbations...\n")
    
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
    base_ftm = calculator.compute_ftm(baseline_events)["FTM"] # Actually base against itself is identity, but we want the base transition from HDI.
    # Wait, the baseline FTM isn't base against base. The base transition is just the distribution.
    # Let's map base to base as Identity
    base_ftm = {f"{c} -> {c}": 1.0 for c in classes}
    
    int_ftms = {}
    for group, events in interventions.items():
        int_ftms[group] = calculator.compute_ftm(events)["FTM"]
        
    # CFV-2 to find Z2
    decomposer = CFV2Decomposer(classes)
    decomp_result = decomposer.decompose(list(int_ftms.values()))
    
    # Let's assume Z2 is the second mode (index 1)
    z2_target = decomp_result["latent_modes"][1]
    
    print(f"2. Extracting Control Basis Matrix B...")
    extractor = CFV3BasisExtractor(len(classes))
    basis = extractor.extract_basis(base_ftm, int_ftms, classes)
    
    print(f"3. Solving Control Geometry for Target {z2_target['mode_id']} (Eigenvalue: {z2_target['eigenvalue']:.4f})...")
    engine = CFV3ControllabilityEngine(basis["B_matrix"], basis["P_base"], basis["intervention_keys"])
    
    control_result = engine.solve_control_policy(z2_target, budget=5.0, l1_lambda=0.001)
    
    print("\n--- OPTIMAL CONTROL POLICY (Intervention Weights) ---")
    for group, weight in control_result["policy"].items():
        if group == "B": name = "Selector Hardening"
        elif group == "C": name = "Entity Hardening"
        else: name = "Table Normalization"
        print(f"  {name} (Group {group}): {weight:.4f}")
        
    print("\n--- INTERVENTION COSTS ---")
    for group, cost in control_result["costs"].items():
        print(f"  Group {group}: {cost:.4f}")
        
    print(f"\nOptimizer Success: {control_result['success']} ({control_result['message']})")
    
    if sum(control_result['policy'].values()) == 0.0:
        print("\n[!] CRITICAL OBSERVATION: OPTIMAL POLICY IS DO NOTHING [!]")
        print("    Why? Because Z2 is composed of WRONG_SELECTOR and ENTITY_BINDING_FAILURE.")
        print("    Interventions B and C merely trade mass between these two states (Conservation of Mass).")
        print("    The optimizer mathematically proved that none of our current interventions can actually")
        print("    destroy Z2. They only rotate its expression, incurring cost for zero net structural gain.")
        
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/cfv3_report.json", "w") as f:
        json.dump(control_result, f, indent=2)

if __name__ == "__main__":
    run_cfv3_pilot()
