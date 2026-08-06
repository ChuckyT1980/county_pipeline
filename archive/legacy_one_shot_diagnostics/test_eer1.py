import json
from vpr2 import VPR2Decision, VendorClass, FailureMode, AcquisitionStrategy
from vpr3 import VPR3Compiler
from eer1 import ExecutionRuntime

def test_eer1_hard_halt():
    compiler = VPR3Compiler()
    runtime = ExecutionRuntime()
    
    # 1. Simulate VPR-2 Decision
    decision = VPR2Decision(
        county="shasta",
        vendor_class=VendorClass.MPTS_HYBRID,
        failure_mode=FailureMode.WAF_BLOCK,
        acquisition_strategy=AcquisitionStrategy.COOKIE_BOOTSTRAP,
        confidence=0.9,
        evidence={},
        risk_flags=["HIGH_WAF_CONFIDENCE"]
    )
    
    # 2. Compile to Graph (VPR-3)
    graph = compiler.compile(decision)
    
    print("--- EER-1 EXECUTING VPR-3 GRAPH ---")
    
    # 3. Execute Graph (EER-1)
    # The target "tax_source" in the dispatchers.py is mocked to hit Shasta's real 403 endpoint
    # to simulate the mid-execution failure.
    telemetry = runtime.execute_graph(graph)
    
    print(json.dumps(telemetry.to_dict(), indent=2))

if __name__ == "__main__":
    test_eer1_hard_halt()
