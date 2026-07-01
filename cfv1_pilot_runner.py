import json
import os
from hdi1_engine import HDI1Engine
from cfv1_engine import CFV1Engine
from cfv1_fri import CFV1FRICalculator

def run_cfv1_pilot():
    print(f"--- PHASE 4A.3: CAUSAL FIX VALIDATION (CFV-1) PILOT ---")
    
    hdi = HDI1Engine()
    cfv = CFV1Engine()
    
    epochs = 400
    print(f"Simulating {epochs} adaptation events through CFV ablation groups...\n")
    
    # 1. Generate Baseline HDI-1 Events (Group A)
    baseline_events = []
    for epoch in range(1, epochs + 1):
        event = hdi.get_next_drift_event()
        event["epoch"] = epoch
        
        # Override synthetic SCR generation so we have enough raw mass to transform
        # We assume for this ablation test, every event generated is a baseline failure
        # so we can track exactly where the failure mass goes.
        event["silent_corruption"] = True 
        baseline_events.append(event)
        
    # 2. Run Interventions (Groups B, C, D)
    interventions = {
        "B": [], # Selector Hardening
        "C": [], # Entity Hardening
        "D": []  # Table Normalization
    }
    
    for base_event in baseline_events:
        for group in interventions.keys():
            # Apply deterministic structural constraint transform
            resolved_type = cfv.resolve_failure(base_event["mutation_type"], group)
            
            # The intervention event preserves the total mass, just changes the type
            int_event = base_event.copy()
            int_event["mutation_type"] = resolved_type
            interventions[group].append(int_event)
            
    # 3. Compute FRI for each group
    calculator = CFV1FRICalculator(baseline_events)
    
    reports = {}
    for group, events in interventions.items():
        reports[group] = calculator.compute_ftm(events)
        
    # 4. Print Results
    for group, report in reports.items():
        if group == "B": name = "Selector Hardening"
        elif group == "C": name = "Entity Hardening"
        else: name = "Table Normalization"
        
        print(f"--- GROUP {group}: {name} ---")
        print("Net Delta SCR:")
        for cls, delta in report["net_deltas"].items():
            sign = "+" if delta > 0 else ""
            print(f"  {cls}: {sign}{delta*100:.2f}%")
            
        print("\nFailure Transfer Matrix (FTM):")
        if not report["FTM"]:
            print("  No failure mass transferred.")
        for transfer, prob in report["FTM"].items():
            print(f"  {transfer}: {prob*100:.2f}% of total mass")
            
        print(f"\nFailure Redistribution Index (FRI): {report['FRI']:.3f}\n")
        
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/cfv1_report.json", "w") as f:
        json.dump(reports, f, indent=2)

if __name__ == "__main__":
    run_cfv1_pilot()
