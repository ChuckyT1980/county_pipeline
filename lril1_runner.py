import json
import os
import time
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from dispatchers_live import LiveDispatcher
from eaf1 import ExecutionAuthorityFirewall
from eer1_schemas import SessionContext
from cars2 import EvaluationVector
from cars2_state import VendorHealthProfile
from cars3_schemas import InstrumentDivergenceFunction, ActionConstraintVector
from cgr1 import ConstraintGeometryResolver
from lril1 import LatentRegimeInferenceLayer
from lril1_assertions import LRILInferenceAssertion

def run_lril1_suite():
    print(f"--- PHASE 3.15: LATENT REGIME INFERENCE TEST (LRIL-1) ---")
    
    alpha = 0.3
    ledger = LRILInferenceAssertion()
    dispatcher = LiveDispatcher()
    lril = LatentRegimeInferenceLayer(velocity_threshold=0.08)
    
    # Hidden CARS-2 Field State (External to LRIL)
    cars2_vsi = 1.0
    cars2_fme = 0.0
    
    for epoch in range(1, 21):
        # Hidden Environment Generation
        noise_injected = False
        if epoch <= 5:
            target_url = "https://example.com"
        elif epoch == 6:
            target_url = "https://example.com"
            noise_injected = True
        elif epoch <= 12:
            target_url = "https://httpstat.us/403"
        else:
            target_url = "https://example.com"
            
        print(f"\n[Epoch {epoch}] Dispatching unannotated step...")
        
        # Dispatch
        step_1 = ExecutionStep(f"s_{epoch}", StepType.HTTP_REQUEST, target_url, {}, 3000, "NONE", ["html"])
        graph = ExecutionGraph("target", "CUSTOM_CMS", "HTTP_ONLY", [step_1], [], ["html"])
        
        # Generate valid ACV via CGR-1 for EAF-1 firewall passage
        eval_vec_dummy = EvaluationVector("dummy", "target", "CUSTOM_CMS", 1.0, 1.0, 0.0, 1.0, 0.0)
        profile_dummy = VendorHealthProfile("CUSTOM_CMS", 1.0, 0.0, 1.0, 0.0)
        idf_dummy = InstrumentDivergenceFunction(0.0, 0.0, 0.0, "NONE->NONE", 0.0)
        acv = ConstraintGeometryResolver.resolve(eval_vec_dummy, profile_dummy, idf_dummy)
        
        payload = ExecutionAuthorityFirewall.compile_payload(graph, acv)
        
        results = dispatcher.execute_graph(payload, SessionContext())
        http_res = results[0]
        
        # Discrete Observation (CVA-1 equivalent)
        if http_res.status == "SUCCESS":
            cva_class = "STABLE_HTTP"
            obs_vsi = 1.0
            obs_fme = 0.0
        else:
            if "TIMEOUT" in str(http_res.error_type):
                cva_class = "TIMEOUT"
            elif "HTTP_ERROR" in str(http_res.error_type) or "WAF_BLOCK" in str(http_res.error_type):
                cva_class = "WAF_BLOCK"
            else:
                cva_class = "NETWORK_ERROR"
            obs_vsi = 0.0
            obs_fme = 1.0
            
        if noise_injected:
            # Overwrite CVA-1 observation manually for epoch 6 to simulate a noisy label
            cva_class = "WAF_BLOCK"
            obs_vsi = 0.0
            obs_fme = 1.0
            
        # Continuous Evolution (CARS-2 equivalent)
        cars2_vsi = (alpha * obs_vsi) + ((1.0 - alpha) * cars2_vsi)
        cars2_fme = (alpha * obs_fme) + ((1.0 - alpha) * cars2_fme)
        
        # --- THE INFERENCE BOUNDARY ---
        # LRIL-1 must infer the world solely from continuous state + categorical labels
        inferred_state = lril.infer(current_vsi=cars2_vsi, current_fme=cars2_fme, current_cva_class=cva_class)
        
        print(f"  -> CVA-1 Label: {cva_class} | CARS-2 VSI: {cars2_vsi:.3f}")
        print(f"  -> LRIL-1 Inference: {inferred_state.regime_label} (dT: {inferred_state.gradient_dt:.3f}, Conf: {inferred_state.confidence:.2f})")
            
        ledger.record_epoch(
            epoch_id=epoch,
            physical_target=target_url,
            cva_class=cva_class,
            lril_regime=inferred_state.regime_label,
            lril_dt=inferred_state.gradient_dt,
            lril_conf=inferred_state.confidence
        )
        
        time.sleep(1)
        
    print("\n--- LRIL-1 COMPLETE. COMPUTING INFERENCE ASSERTIONS ---")
    report = ledger.compute_report()
    
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/lril1_inference_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(json.dumps(report, indent=2))
    print(f"\nFinal LRIL-1 Status: {report['lril1_inference_status']}")

if __name__ == "__main__":
    run_lril1_suite()
