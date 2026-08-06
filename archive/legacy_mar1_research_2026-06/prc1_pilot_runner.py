import json
import os
from hdi1_engine import HDI1Engine
from prc1_analyzer import PRC1Analyzer
from prc1_assertions import PRC1Assertion

def run_prc1_pilot():
    print(f"--- PHASE 4A.2: PREDICTIVE RISK CALIBRATION (PRC-1) PILOT ---")
    
    hdi_engine = HDI1Engine()
    ledger = []
    
    epochs = 200
    print(f"Simulating {epochs} adaptation events using Hybrid Drift Injection Model (HDI-1)...\n")
    
    for epoch in range(1, epochs + 1):
        event = hdi_engine.get_next_drift_event()
        event["epoch"] = epoch
        ledger.append(event)
        
    analyzer = PRC1Analyzer(ledger)
    
    # Compute SCR by PRS Bucket
    scr_by_bucket = analyzer.get_scr_by_prs_bucket()
    print("--- SCR RATE BY PRS BUCKET ---")
    for b in scr_by_bucket:
        print(f"  {b['bucket']}: {b['scr_rate'] * 100:.2f}% (Attempts: {b['attempts']})")
        
    # Compute Attribution x Risk Matrix
    matrix = analyzer.get_attribution_risk_matrix()
    print("\n--- ATTRIBUTION × RISK MATRIX ---")
    for cls, avg_prs in matrix.items():
        print(f"  {cls}: Avg PRS = {avg_prs:.2f}")
        
    # Compute Assertions
    assertion = PRC1Assertion(analyzer)
    report = assertion.compute_report()
    
    print("\n--- PRC-1 GRADUATION REPORT ---")
    print(json.dumps(report, indent=2))
    
    print(f"\nFinal PRC-1 Status: {report['prc1_calibration_status']}")
    
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/prc1_ledger.jsonl", "w") as f:
        for entry in ledger:
            f.write(json.dumps(entry) + "\n")

if __name__ == "__main__":
    run_prc1_pilot()
