import json
import os
import time
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from dispatchers_live import LiveDispatcher
from eer1_schemas import SessionContext
from oni1 import NullStateInferenceEngine
from oni1_assertions import ONINullStateAssertion

def run_oni1_suite():
    print(f"--- PHASE 3.16: OBSERVATIONAL NULL-STATE INFERENCE TEST (ONI-1) ---")
    
    alpha = 0.3
    ledger = ONINullStateAssertion()
    dispatcher = LiveDispatcher()
    oni = NullStateInferenceEngine(velocity_threshold=0.08, decay_lambda=0.5)
    
    # Hidden CARS-2 Field State (External to LRIL)
    cars2_vsi = 1.0
    cars2_fme = 0.0
    
    for epoch in range(1, 13):
        telemetry_dropped = False
        if epoch <= 5:
            target_url = "https://example.com"
        elif epoch <= 8:
            target_url = "https://example.com"
            telemetry_dropped = True # Total blackout
        else:
            target_url = "https://httpstat.us/403"
            
        print(f"\n[Epoch {epoch}] Dispatching unannotated step... (Dropped: {telemetry_dropped})")
        
        # Dispatch
        step_1 = ExecutionStep(f"s_{epoch}", StepType.HTTP_REQUEST, target_url, {}, 3000, "NONE", ["html"])
        graph = ExecutionGraph("target", "CUSTOM_CMS", "HTTP_ONLY", [step_1], [], ["html"])
        
        if not telemetry_dropped:
            # We bypass EAF-1 for this test since we are isolating inference
            # (No dummy ACV generation needed here because we are not testing EAF-1 boundary,
            # but LiveDispatcher expects a payload. We'll just construct dummy to pass EAF.)
            from eaf1 import ExecutionAuthorityFirewall
            from cars2 import EvaluationVector
            from cars2_state import VendorHealthProfile
            from cars3_schemas import InstrumentDivergenceFunction
            from cgr1 import ConstraintGeometryResolver
            
            eval_vec_dummy = EvaluationVector("dummy", "target", "CUSTOM_CMS", 1.0, 1.0, 0.0, 1.0, 0.0)
            profile_dummy = VendorHealthProfile("CUSTOM_CMS", 1.0, 0.0, 1.0, 0.0)
            idf_dummy = InstrumentDivergenceFunction(0.0, 0.0, 0.0, "NONE->NONE", 0.0)
            acv = ConstraintGeometryResolver.resolve(eval_vec_dummy, profile_dummy, idf_dummy)
            payload = ExecutionAuthorityFirewall.compile_payload(graph, acv)
            
            results = dispatcher.execute_graph(payload, SessionContext())
            http_res = results[0]
            
            # Discrete Observation
            if http_res.status == "SUCCESS":
                cva_class = "STABLE_HTTP"
                obs_vsi = 1.0
                obs_fme = 0.0
            else:
                if "HTTP_ERROR" in str(http_res.error_type) or "WAF_BLOCK" in str(http_res.error_type):
                    cva_class = "WAF_BLOCK"
                elif "TIMEOUT" in str(http_res.error_type):
                    cva_class = "TIMEOUT"
                else:
                    cva_class = "NETWORK_ERROR"
                obs_vsi = 0.0
                obs_fme = 1.0
                
            # Continuous Evolution
            cars2_vsi = (alpha * obs_vsi) + ((1.0 - alpha) * cars2_vsi)
            cars2_fme = (alpha * obs_fme) + ((1.0 - alpha) * cars2_fme)
            
            # Inference call with data
            inferred_state = oni.infer_with_null_handling(current_vsi=cars2_vsi, current_fme=cars2_fme, current_cva_class=cva_class)
            print(f"  -> CVA-1 Label: {cva_class} | CARS-2 VSI: {cars2_vsi:.3f}")
        else:
            # Telemetry Blackout (None values)
            cva_class = None
            
            # Inference call without data
            inferred_state = oni.infer_with_null_handling(current_vsi=None, current_fme=None, current_cva_class=None)
            print(f"  -> CVA-1 Label: <SILENCE> | CARS-2 VSI: <FROZEN at {cars2_vsi:.3f}>")
            
        print(f"  -> ONI-1 Inference: {inferred_state.regime_label} (dT: {inferred_state.gradient_dt:.3f}, Conf: {inferred_state.confidence:.3f})")
            
        ledger.record_epoch(
            epoch_id=epoch,
            physical_target=target_url,
            telemetry_dropped=telemetry_dropped,
            oni_regime=inferred_state.regime_label,
            oni_dt=inferred_state.gradient_dt,
            oni_conf=inferred_state.confidence
        )
        
        time.sleep(1)
        
    print("\n--- ONI-1 COMPLETE. COMPUTING NULL-STATE ASSERTIONS ---")
    report = ledger.compute_report()
    
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/oni1_null_state_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(json.dumps(report, indent=2))
    print(f"\nFinal ONI-1 Status: {report['oni1_null_state_status']}")

if __name__ == "__main__":
    run_oni1_suite()
