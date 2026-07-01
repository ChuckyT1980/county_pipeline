import json
import os
import time
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from cars3_schemas import InstrumentDivergenceFunction, ActionConstraintVector
from cars2 import EvaluationVector
from cars2_state import VendorHealthProfile
from cgr1 import ConstraintGeometryResolver
from eaf1 import ExecutionAuthorityFirewall
from dispatchers_live import LiveDispatcher
from eer1_schemas import SessionContext
from rbd1_assertions import RBDBoundaryDriftAssertion

def run_rbd1_suite():
    print(f"--- PHASE 3.14: REGIME BOUNDARY DRIFT STABILITY TEST (RBD-1) ---")
    
    alpha = 0.3
    ledger = RBDBoundaryDriftAssertion(alpha=alpha)
    dispatcher = LiveDispatcher()
    
    vendor_class = "CUSTOM_CMS"
    profile = VendorHealthProfile(vendor_class, 1.0, 0.0, 1.0, 0.0)
    idf = InstrumentDivergenceFunction(delta_efs=0.0, delta_vsi=0.0, delta_fme=0.0, transition_label="NONE->NONE", ivd=0.0)
    
    # Initial CARS-2 State
    cars2_vsi = 1.0
    cars2_fme = 0.0
    
    for epoch in range(1, 16):
        if epoch <= 5:
            target_url = "https://example.com"
            regime = "STABLE_HTTP"
        elif epoch <= 10:
            target_url = "https://httpstat.us/403"
            regime = "WAF_BLOCK"
        else:
            target_url = "https://httpstat.us/200?sleep=5000"
            regime = "TIMEOUT"
            
        print(f"\n[Epoch {epoch}] Regime: {regime} | Target: {target_url}")
        
        # 1. Update EvaluationVector from EMA State
        eval_vec = EvaluationVector("rbd1", "target", vendor_class, cars2_vsi, cars2_vsi, cars2_fme, cars2_vsi, cars2_fme)
        
        # 2. CGR-1 Constraint Resolution
        acv: ActionConstraintVector = ConstraintGeometryResolver.resolve(eval_vec, profile, idf)
        http_weight = acv.instrument_authority_weights.get("HTTP", 0.0)
        
        print(f"  -> CGR-1 HTTP Weight: {http_weight:.3f} | CARS-2 VSI: {cars2_vsi:.3f} | FME: {cars2_fme:.3f}")
        
        # 3. VPR-3
        step_1 = ExecutionStep(f"s_epoch_{epoch}", StepType.HTTP_REQUEST, target_url, {}, 3000, "NONE", ["html"])
        graph = ExecutionGraph("target", vendor_class, "HTTP_ONLY", [step_1], [], ["html"])
        
        # 4. EAF-1
        eaf1_success = False
        try:
            payload = ExecutionAuthorityFirewall.compile_payload(graph, acv)
            eaf1_success = True
        except Exception as e:
            print(f"  -> EAF-1 Exception: {e}")
            payload = None
            
        if not payload:
            continue
            
        # 5. Live Dispatcher
        results = dispatcher.execute_graph(payload, SessionContext())
        http_res = results[0]
        
        # 6. CVA-1 Classification (Observation)
        if http_res.status == "SUCCESS":
            cva_class = "STABLE_HTTP"
            obs_vsi = 1.0
            obs_fme = 0.0
        else:
            if "TIMEOUT" in str(http_res.error_type):
                cva_class = "TIMEOUT"
            elif "HTTP_ERROR" in str(http_res.error_type):
                cva_class = "WAF_BLOCK"
            else:
                cva_class = "NETWORK_ERROR"
            obs_vsi = 0.0
            obs_fme = 1.0
            
        print(f"  -> CVA-1 Observation: {cva_class} (Observed VSI: {obs_vsi}, FME: {obs_fme})")
            
        # 7. Assertion Record
        ledger.record_epoch(
            epoch_id=epoch,
            target_url=target_url,
            cva_class=cva_class,
            vsi=cars2_vsi,
            fme=cars2_fme,
            http_weight=http_weight,
            eaf1_success=eaf1_success
        )
        
        # 8. CARS-2 EMA Update for next epoch
        cars2_vsi = (alpha * obs_vsi) + ((1.0 - alpha) * cars2_vsi)
        cars2_fme = (alpha * obs_fme) + ((1.0 - alpha) * cars2_fme)
        
        time.sleep(1) # Be gentle on public APIs
        
    print("\n--- RBD-1 COMPLETE. COMPUTING DRIFT ASSERTIONS ---")
    report = ledger.compute_report()
    
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/rbd1_drift_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(json.dumps(report, indent=2))
    print(f"\nFinal RBD-1 Status: {report['rbd1_drift_status']}")

if __name__ == "__main__":
    run_rbd1_suite()
