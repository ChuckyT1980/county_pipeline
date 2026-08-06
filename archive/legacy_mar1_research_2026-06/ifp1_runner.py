import json
import os
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from cars3_schemas import InstrumentDivergenceFunction, ActionConstraintVector
from cars2 import EvaluationVector
from cars2_state import VendorHealthProfile
from cgr1 import ConstraintGeometryResolver
from eaf1 import ExecutionAuthorityFirewall
from dispatchers_live import LiveDispatcher
from eer1_schemas import SessionContext
from ifp1_assertions import IFPPropagationAssertion

def run_ifp1_suite():
    print(f"--- PHASE 3.13: INTRA-GRAPH FAILURE PROPAGATION TEST (IFP-1) ---")
    
    ledger = IFPPropagationAssertion()
    dispatcher = LiveDispatcher()
    
    print("\n[TEST] Compiling composite execution DAG with embedded failure...")
    
    # 1. Base Strategy
    vendor_class = "CUSTOM_CMS"
    profile = VendorHealthProfile(vendor_class, 1.0, 0.0, 1.0, 0.0)
    eval_vec = EvaluationVector("ifp1", "target", vendor_class, 1.0, 1.0, 0.0, 1.0, 0.0)
    idf = InstrumentDivergenceFunction(delta_efs=0.0, delta_vsi=0.0, delta_fme=0.0, transition_label="NONE->NONE", ivd=0.0)
    
    acv: ActionConstraintVector = ConstraintGeometryResolver.resolve(eval_vec, profile, idf)
    
    # 2. Compositional VPR-3 Graph
    # Step 1: Clean HTTP
    s1 = ExecutionStep("s1_clean_http", StepType.HTTP_REQUEST, "https://example.com", {}, 3000, "NONE", ["html"])
    # Step 2: Clean Browser
    s2 = ExecutionStep("s2_clean_browser", StepType.BROWSER_NAVIGATE, "https://example.org", {}, 10000, "NONE", ["html"])
    # Step 3: Fatal Timeout
    s3 = ExecutionStep("s3_fatal_timeout", StepType.HTTP_REQUEST, "https://httpstat.us/200?sleep=5000", {}, 2000, "NONE", ["html"])
    # Step 4: Clean HTTP (Should be Unexecuted)
    s4 = ExecutionStep("s4_unexecuted", StepType.HTTP_REQUEST, "https://example.com", {}, 3000, "NONE", ["html"])
    
    graph = ExecutionGraph("ifp_target", vendor_class, "HYBRID_RENDER_PIPE", [s1, s2, s3, s4], [], ["html"])
    
    # 3. Compile EAF-1
    payload = ExecutionAuthorityFirewall.compile_payload(graph, acv)
    
    # 4. Dispatch (EER-1 / DDL-1)
    print("\n[TEST] Dispatching compositional graph. Expecting mid-graph abort...")
    results = dispatcher.execute_graph(payload, SessionContext())
    
    # 5. Classify (CVA-1 mapping)
    cva_classes = []
    for res in results:
        if res.status == "SUCCESS":
            cva_classes.append("STABLE_HTTP")
        else:
            if "TIMEOUT" in str(res.error_type):
                cva_classes.append("TIMEOUT")
            elif "HTTP_ERROR" in str(res.error_type):
                cva_classes.append("WAF_BLOCK")
            else:
                cva_classes.append("NETWORK_ERROR")
                
    # 6. Assertion
    ledger.record_run(
        graph=graph,
        results=results,
        eaf1_hash=payload.integrity_hash,
        cva1_classes=cva_classes
    )
    
    print("\n--- IFP-1 COMPLETE. COMPUTING PROPAGATION ASSERTIONS ---")
    report = ledger.compute_report()
    
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/ifp1_propagation_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(json.dumps(report, indent=2))
    print(f"\nFinal IFP-1 Status: {report['ifp1_propagation_status']}")

if __name__ == "__main__":
    run_ifp1_suite()
