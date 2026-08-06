from vpr3 import ExecutionGraph, ExecutionStep, StepType
from eer1_schemas import SessionContext
from dispatchers_live import LiveDispatcher

def test_stage_3a_live_execution():
    dispatcher = LiveDispatcher()
    
    print("--- PHASE 3 STAGE 3A: LIVE ACTUATOR EXECUTION (HTTP ONLY) ---\n")
    
    # We will test against two public endpoints to observe real entropy.
    # 1. A valid endpoint (example.com) to prove success.
    # 2. A simulated timeout or WAF block endpoint (httpstat.us) to prove failure bubbling.
    
    # 1. SUCCESS GRAPH
    print("Scenario 1: Live HTTP Fetch (example.com)")
    step_success = ExecutionStep("S1", StepType.HTTP_REQUEST, "http://example.com", {}, 5000, "NONE", [])
    session1 = SessionContext()
    
    res1 = dispatcher.execute(step_success, session1)
    print(f"  Result: {res1.status} | Latency: {res1.latency_ms}ms")
    print(f"  Raw Body Preview: {res1.response.get('raw_body', '')[:60]}...\n")
    
    # 2. TIMEOUT GRAPH
    print("Scenario 2: Live HTTP Timeout (httpstat.us/200?sleep=5000 with 1000ms timeout)")
    step_timeout = ExecutionStep("S2", StepType.HTTP_REQUEST, "https://httpstat.us/200?sleep=5000", {}, 1000, "NONE", [])
    session2 = SessionContext()
    
    res2 = dispatcher.execute(step_timeout, session2)
    print(f"  Result: {res2.status} | Error: {res2.error_type}")
    print(f"  Raw Body (Empty): {res2.response.get('raw_body', '')}\n")
    
    # 3. WAF/403 GRAPH
    print("Scenario 3: Live HTTP 403 / WAF Block (httpbin.org/status/403)")
    step_waf = ExecutionStep("S3", StepType.HTTP_REQUEST, "https://httpbin.org/status/403", {}, 5000, "NONE", [])
    session3 = SessionContext()
    
    res3 = dispatcher.execute(step_waf, session3)
    print(f"  Result: {res3.status} | Error: {res3.error_type}")
    print(f"  Status Code: {res3.response.get('status_code', '')}\n")

if __name__ == "__main__":
    test_stage_3a_live_execution()
