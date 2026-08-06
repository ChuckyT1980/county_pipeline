import json
from vpr2 import VPR2Decision, VendorClass, FailureMode, AcquisitionStrategy
from vpr3 import VPR3Compiler
from telemetry import ExecutionTelemetry

def test_vpr3_compilation():
    compiler = VPR3Compiler()
    
    # Simulate the VPR-2 decision from earlier tests
    decision = VPR2Decision(
        county="shasta",
        vendor_class=VendorClass.MPTS_HYBRID,
        failure_mode=FailureMode.WAF_BLOCK,
        acquisition_strategy=AcquisitionStrategy.COOKIE_BOOTSTRAP,
        confidence=0.9,
        evidence={},
        risk_flags=["HIGH_WAF_CONFIDENCE"]
    )
    
    print("--- VPR-3 COMPILATION: COOKIE_BOOTSTRAP ---")
    graph = compiler.compile(decision)
    print(json.dumps(graph.to_dict(), indent=2))
    
    # Simulate a successful telemetry execution matching the plan
    telemetry = ExecutionTelemetry(
        county="shasta",
        strategy_planned="COOKIE_BOOTSTRAP",
        strategy_executed="COOKIE_BOOTSTRAP",
        step_trace=[
            {"step_id": "S1", "type": "COOKIE_INIT", "status": "SUCCESS"},
            {"step_id": "S2", "type": "HTTP_REQUEST", "status": "SUCCESS"}
        ],
        failure_step=None,
        failure_reason=None,
        execution_path_hash="hash123",
        apns_extracted=50,
        apns_validated=45,
        compliance_flags=[]
    )
    
    print("\n--- EXECUTION TELEMETRY ---")
    print(json.dumps(telemetry.to_dict(), indent=2))

if __name__ == "__main__":
    test_vpr3_compilation()
