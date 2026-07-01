import json
import os
from hdi1_engine import HDI1Engine
from cfv1_engine import CFV1Engine
from cfv1_fri import CFV1FRICalculator
from cfv2_decomposer import CFV2Decomposer
from cfv2_metrics import CFV2MetricsEngine

def run_cfv2_pilot():
    print(f"--- PHASE 4A.4: CFV-2 FAILURE MANIFOLD DECOMPOSITION PILOT ---")
    
    hdi = HDI1Engine()
    cfv = CFV1Engine()
    classes = ["WRONG_SELECTOR", "TABLE_SHIFT", "ENTITY_BINDING_FAILURE", "NEIGHBOR_FIELD_CAPTURE"]
    
    epochs = 400
    print(f"Simulating {epochs} adaptation events through CFV-1 ablation to extract FTMs...\n")
    
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
            
    # Extract FTMs
    calculator = CFV1FRICalculator(baseline_events)
    ftms = []
    for group, events in interventions.items():
        report = calculator.compute_ftm(events)
        ftms.append(report["FTM"])
        
    print("Feeding FTM tensors into CFV-2 Algebraic Decomposer...")
    decomposer = CFV2Decomposer(classes)
    decomp_result = decomposer.decompose(ftms)
    
    print("\n--- LATENT FAILURE ATTRACTORS (Z_i) ---")
    for mode in decomp_result["latent_modes"]:
        print(f"  {mode['mode_id']} (Eigenvalue = {mode['eigenvalue']:.4f})")
        for cls, mass in mode["distribution"].items():
            if mass > 0.05: # Only show significant mass
                print(f"    -> {cls}: {mass*100:.1f}%")
                
    metrics = CFV2MetricsEngine(decomp_result["latent_modes"])
    
    print("\n--- LATENT FAILURE RANK (LFR) ---")
    lfr = metrics.compute_lfr()
    for rank in lfr:
        print(f"  {rank['mode_id']}: {rank['lfr_score']:.4f} (Primary Surface: {rank['primary_surface_manifestation']})")
        
    print("\n--- NON-IDENTIFIABILITY SCORE (NIS) ---")
    nis = metrics.compute_nis(classes)
    for pair, score in nis["nis_matrix"].items():
        # High score means the two modes project similarly in latent space
        print(f"  {pair}: {score:.4f}")
        
    if nis["highly_coupled_defects"]:
        print("\n[!] WARNING: Highly Coupled Surface Defects Found (NIS > 0.85):")
        for pair, score in nis["highly_coupled_defects"].items():
            print(f"  {pair}: {score:.4f} -> These are likely the SAME latent defect.")
            
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/cfv2_report.json", "w") as f:
        json.dump({
            "decomposition": decomp_result,
            "lfr": lfr,
            "nis": nis
        }, f, indent=2)
        
    print("\nCFV-2 Manifold Decomposition Complete.")

if __name__ == "__main__":
    run_cfv2_pilot()
