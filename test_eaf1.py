from vpr3 import ExecutionGraph, ExecutionStep, StepType
from cars3_schemas import ActionConstraintVector, ExecutionMode
from eaf1_schemas import AuthorizedExecutionPayload, ExecutionAuthorityViolation
from eaf1 import ExecutionAuthorityFirewall
from dispatchers_live import LiveDispatcher
from eer1_schemas import SessionContext

def test_eaf1_gate():
    print("--- PHASE 3.9: EAF-1 VALIDATION ---")
    
    # Setup graphs
    step_http = ExecutionStep("s1", StepType.HTTP_REQUEST, "http://example.com", {}, 1000, "NONE", ["html"])
    graph_http = ExecutionGraph("county", "vendor", "HTTP_ONLY", [step_http], [], ["html"])
    
    step_browser = ExecutionStep("s2", StepType.BROWSER_NAVIGATE, "http://example.com", {}, 1000, "NONE", ["html"])
    graph_browser = ExecutionGraph("county", "vendor", "BROWSER_ONLY", [step_browser], [], ["html"])

    # 1. ACV with 0.0 HTTP Authority
    acv_no_http = ActionConstraintVector(
        allowed_strategies=["HTTP_ONLY", "BROWSER_ONLY"], # Physically allowed strategy
        retry_budget=0,
        escalation_threshold=1.0,
        vendor_class_lock=None,
        execution_mode=ExecutionMode.FULL,
        confidence_floor=0.5,
        entropy_cap=1.0,
        instrument_authority_weights={"HTTP": 0.0, "PLAYWRIGHT": 1.0} # ...but 0.0 trust in the instrument
    )
    
    print("\n[TEST 1] Attempting to compile HTTP Graph under 0.0 HTTP Authority weight...")
    try:
        ExecutionAuthorityFirewall.compile_payload(graph_http, acv_no_http)
        print("FAIL: EAF-1 allowed compilation of 0.0 weighted instrument.")
    except ExecutionAuthorityViolation as e:
        print(f"SUCCESS: EAF-1 blocked compilation. Reason: {str(e)}")

    print("\n[TEST 2] Attempting to compile Browser Graph under same 1.0 Playwright weight...")
    payload = ExecutionAuthorityFirewall.compile_payload(graph_browser, acv_no_http)
    print(f"SUCCESS: Payload generated. Hash: {payload.integrity_hash}")

    print("\n[TEST 3] Dispatching AuthorizedPayload to locked EER-1...")
    dispatcher = LiveDispatcher()
    
    try:
        # Expected to work up until it hits network reality
        res = dispatcher.execute_graph(payload, SessionContext())
        print(f"SUCCESS: Dispatcher accepted payload and executed steps. (Len: {len(res)})")
    except ExecutionAuthorityViolation as e:
        print(f"FAIL: Dispatcher rejected valid payload: {e}")

    print("\n[TEST 4] Mutating payload post-compilation (Simulating rogue runtime logic)...")
    payload.constraint_vector.execution_mode = ExecutionMode.STRICT
    
    try:
        dispatcher.execute_graph(payload, SessionContext())
        print("FAIL: Dispatcher allowed mutated payload to execute.")
    except ExecutionAuthorityViolation as e:
        print(f"SUCCESS: EER-1 ABORTED. Reason: {e}")

if __name__ == "__main__":
    test_eaf1_gate()
