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
from cit1_assertions import CITInvarianceAssertion

def run_cit1_suite(n_iterations: int = 20):
    print(f"--- PHASE 3.11: CLOSURE INVARIANCE TEST (CIT-1) ---")
    print(f"Target: los_angeles | N={n_iterations} iterations\n")
    
    ledger = CITInvarianceAssertion()
    
    # Target definition
    target_url = "https://assessor.lacounty.gov/"
    vendor_class = "CUSTOM_CMS"
    
    print("Initiating full-stack execution loops...")
    
    # Instantiate Dispatcher once so Playwright engine persists across loops
    # DDL-1 guarantees context and page are destroyed per-step inside the actuator
    dispatcher = LiveDispatcher()
    
    for i in range(n_iterations):
        print(f"  -> Iteration {i+1}/{n_iterations} running...")
        
        # 1. Constant Environmental Epistemic Input (Simulate stable geometry input to isolate execution)
        profile = VendorHealthProfile(vendor_class, 1.0, 0.0, 1.0, 0.0)
        eval_vec = EvaluationVector("cit1", "los_angeles", vendor_class, 1.0, 1.0, 0.0, 1.0, 0.0)
        idf = InstrumentDivergenceFunction(delta_efs=0.0, delta_vsi=0.0, delta_fme=0.0, transition_label="NONE->NONE", ivd=0.0)
        
        # 2. Constraint Geometry Resolver (CGR-1)
        acv: ActionConstraintVector = ConstraintGeometryResolver.resolve(eval_vec, profile, idf)
        
        # 3. Virtual Pipeline Recompiler (VPR-3)
        # We define a stable Hybrid graph. Both HTTP and Playwright must fire identically.
        step_1 = ExecutionStep("s_http", StepType.HTTP_REQUEST, target_url, {}, 5000, "NONE", ["html"])
        step_2 = ExecutionStep("s_browser", StepType.BROWSER_NAVIGATE, target_url, {}, 10000, "NONE", ["html"])
        graph = ExecutionGraph("los_angeles", vendor_class, "HYBRID_RENDER_PIPE", [step_1, step_2], [], ["html"])
        
        # 4. Execution Authority Firewall (EAF-1)
        payload = ExecutionAuthorityFirewall.compile_payload(graph, acv)
        
        # 5. Live Dispatcher (EER-1/DDL-1)
        results = dispatcher.execute_graph(payload, SessionContext())
        
        # 6. Classification & Vectors (CVA-1/CARS-2)
        http_res = results[0]
        cva_class = "STABLE_HTTP" if http_res.status == "SUCCESS" else "NETWORK_ERROR"
        
        # Synthetic translation to CARS-2 for observation variance (simplified for CIT-1)
        vsi = 1.0 if cva_class == "STABLE_HTTP" else 0.0
        fme = 0.0 if cva_class == "STABLE_HTTP" else 1.0
        
        # 7. Log to Assertion Ledger
        ledger.record_run(
            cgr1_strategies=acv.allowed_strategies,
            cgr1_weights=acv.instrument_authority_weights.copy(),
            eaf1_hash=payload.integrity_hash,
            cva1_class=cva_class,
            vsi=vsi,
            fme=fme
        )
        
        # Sleep slightly to avoid overwhelming target and ensure socket clearance
        time.sleep(1)
        
    print("\n--- TEST COMPLETE. COMPUTING INVARIANCE ASSERTIONS ---")
    report = ledger.compute_report()
    
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/invariance_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(json.dumps(report, indent=2))
    print(f"\nFinal CIT-1 Status: {report['cit1_closure_status']}")

if __name__ == "__main__":
    run_cit1_suite(n_iterations=20)
