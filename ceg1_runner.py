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
from ceg1_assertions import CEGGeneralizationAssertion

def run_ceg1_suite():
    print(f"--- PHASE 3.12: CROSS-ENTROPY GENERALIZATION TEST (CEG-1) ---")
    
    ledger = CEGGeneralizationAssertion()
    
    # 1. The Multi-Regime Matrix (Real Public Targets)
    regimes = {
        "STABLE_HTTP": "https://example.com",
        "WAF_BLOCK": "https://httpstat.us/403",
        "TIMEOUT": "https://httpstat.us/200?sleep=5000",
        "REDIRECT": "https://httpstat.us/302"
    }
    
    vendor_class = "CUSTOM_CMS"
    
    # Instantiate Dispatcher once
    dispatcher = LiveDispatcher()
    
    for regime_name, target_url in regimes.items():
        print(f"\n[REGIME: {regime_name}] Probing {target_url}...")
        
        for i in range(3): # N=3 per regime is enough for CEG-1 structural stationarity check
            print(f"  -> Sample {i+1}/3")
            
            # 1. Constant Environmental Epistemic Input (Hold Policy Constant)
            profile = VendorHealthProfile(vendor_class, 1.0, 0.0, 1.0, 0.0)
            eval_vec = EvaluationVector("ceg1", "target", vendor_class, 1.0, 1.0, 0.0, 1.0, 0.0)
            idf = InstrumentDivergenceFunction(delta_efs=0.0, delta_vsi=0.0, delta_fme=0.0, transition_label="NONE->NONE", ivd=0.0)
            
            # 2. CGR-1 (Must resolve without crashing and produce identical policy)
            acv: ActionConstraintVector = ConstraintGeometryResolver.resolve(eval_vec, profile, idf)
            
            # 3. VPR-3
            # We enforce a timeout of 3000ms to ensure the TIMEOUT regime actually triggers an internal timeout
            step_1 = ExecutionStep("s_http", StepType.HTTP_REQUEST, target_url, {}, 3000, "NONE", ["html"])
            graph = ExecutionGraph("target", vendor_class, "HTTP_ONLY", [step_1], [], ["html"])
            
            # 4. EAF-1
            eaf1_success = False
            try:
                payload = ExecutionAuthorityFirewall.compile_payload(graph, acv)
                eaf1_success = True
            except Exception as e:
                print(f"EAF-1 Exception: {e}")
                payload = None
                
            if not payload:
                continue
                
            # 5. Live Dispatcher
            results = dispatcher.execute_graph(payload, SessionContext())
            http_res = results[0]
            print(f"      [Debug] Status: {http_res.status}, ErrorType: {http_res.error_type}")
            
            # 6. Classification & Vectors
            # Direct semantic map based on HTTP rules (since CVA-1 is just logic in this testing scope)
            if http_res.status == "SUCCESS":
                cva_class = "STABLE_HTTP"
            else:
                if "TIMEOUT" in str(http_res.error_type):
                    cva_class = "TIMEOUT"
                elif "HTTP_ERROR" in str(http_res.error_type):
                    cva_class = "WAF_BLOCK"
                else:
                    cva_class = "NETWORK_ERROR"
            
            # Map observational variance (CARS-2)
            vsi = 1.0 if cva_class == "STABLE_HTTP" else 0.0
            fme = 1.0 if cva_class in ["TIMEOUT", "WAF_BLOCK", "NETWORK_ERROR"] else 0.0
            
            # 7. Log to Assertion Ledger
            ledger.record_run(
                regime_name=regime_name,
                cgr1_strategies=acv.allowed_strategies,
                cgr1_weights=acv.instrument_authority_weights.copy(),
                eaf1_success=eaf1_success,
                cva1_class=cva_class,
                vsi=vsi,
                fme=fme
            )
            
            time.sleep(1) # Prevent rate limiting
            
    print("\n--- CEG-1 COMPLETE. COMPUTING GENERALIZATION ASSERTIONS ---")
    report = ledger.compute_report()
    
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/ceg1_generalization_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(json.dumps(report, indent=2))
    print(f"\nFinal CEG-1 Status: {report['ceg1_generalization_status']}")

if __name__ == "__main__":
    run_ceg1_suite()
