import json
from cva1 import ConstraintViolationAuditor
from cva1_schemas import ViolationType
from eer1_schemas import RuntimeTelemetry, ExecutionResult
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from cars3_schemas import ActionConstraintVector, ExecutionMode
from cars2_state import HealthEstimator
from cars2 import StatelessEvaluator, EvaluationVector

def test_cva1_quarantine():
    evaluator = StatelessEvaluator()
    state_tracker = HealthEstimator(alpha=0.5)
    
    # Base setup
    step = ExecutionStep(id="S1", type=StepType.HTTP_REQUEST, target="http://example.com", params={}, timeout_ms=1000, retry_policy="NONE", outputs=[])
    graph = ExecutionGraph("HTTP_ONLY", "CUSTOM_CMS", "HTTP_ONLY", [step], [], [])
    acv = ActionConstraintVector(["HTTP_ONLY"], 0, 1.0, None, ExecutionMode.FULL, 0.9, 0.75)
    vendor_class = "CUSTOM_CMS"

    print("--- CVA-1 TEST: SCHEMA DRIFT QUARANTINE ---\n")
    
    # RUN 1: Perfect Execution
    t1 = RuntimeTelemetry("g1", [ExecutionResult("S1", "SUCCESS", {}, 100, None, None)], "HTTP_ONLY", "HTTP_ONLY", None, 100, {})
    raw_responses_1 = [{"mock_is_captcha": False, "mock_is_redesign": False}]
    
    report1 = ConstraintViolationAuditor.verify(t1, graph, acv, raw_responses_1)
    print(f"RUN 1: {report1.violation_type.value} -> Quarantine? {report1.quarantine_execution}")
    
    v1 = evaluator.evaluate(t1, "countyX", vendor_class)
    p1 = state_tracker.ingest(v1, quarantine=report1.quarantine_execution)
    print(f"  EMA_VSI: {p1.ema_vsi:.2f} | Buffer Size: {len(state_tracker.anomaly_buffer)}\n")
    
    # RUN 2: Soft Schema Drift (CAPTCHA on 200 OK)
    t2 = RuntimeTelemetry("g2", [ExecutionResult("S1", "SUCCESS", {}, 150, None, None)], "HTTP_ONLY", "HTTP_ONLY", None, 150, {})
    raw_responses_2 = [{"mock_is_captcha": True, "mock_is_redesign": False}]
    
    report2 = ConstraintViolationAuditor.verify(t2, graph, acv, raw_responses_2)
    print(f"RUN 2: {report2.violation_type.value} -> Quarantine? {report2.quarantine_execution}")
    
    v2 = evaluator.evaluate(t2, "countyX", vendor_class)
    p2 = state_tracker.ingest(v2, quarantine=report2.quarantine_execution)
    print(f"  EMA_VSI: {p2.ema_vsi:.2f} (EMA Frozen!) | Buffer Size: {len(state_tracker.anomaly_buffer)}\n")
    
    # RUN 3: Hard Schema Break (Redesign)
    t3 = RuntimeTelemetry("g3", [ExecutionResult("S1", "SUCCESS", {}, 120, None, None)], "HTTP_ONLY", "HTTP_ONLY", None, 120, {})
    raw_responses_3 = [{"mock_is_captcha": False, "mock_is_redesign": True}]
    
    report3 = ConstraintViolationAuditor.verify(t3, graph, acv, raw_responses_3)
    print(f"RUN 3: {report3.violation_type.value} -> Quarantine? {report3.quarantine_execution}")
    
    v3 = evaluator.evaluate(t3, "countyX", vendor_class)
    p3 = state_tracker.ingest(v3, quarantine=report3.quarantine_execution)
    print(f"  EMA_VSI: {p3.ema_vsi:.2f} (EMA Frozen!) | Buffer Size: {len(state_tracker.anomaly_buffer)}\n")

if __name__ == "__main__":
    test_cva1_quarantine()
