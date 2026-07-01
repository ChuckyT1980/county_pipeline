import json
from eer1_schemas import RuntimeTelemetry, ExecutionResult
from cars2 import StatelessEvaluator
from cars2_state import HealthEstimator
from cars2_aggregator import DashboardAggregator

def test_cars2_pipeline():
    evaluator = StatelessEvaluator()
    state_tracker = HealthEstimator(alpha=0.3)
    
    vendor = "MPTS_HYBRID"
    
    print("--- SIMULATING TELEMETRY STREAM ---\n")
    
    # Run 1: Perfect Execution
    t1 = RuntimeTelemetry(
        execution_graph_id="g1",
        step_results=[
            ExecutionResult("S1", "SUCCESS", {}, 100, None, None),
            ExecutionResult("S2", "SUCCESS", {}, 100, None, None)
        ],
        strategy_planned="HTTP_ONLY",
        strategy_observed="HTTP_ONLY",
        failure_step=None,
        total_latency_ms=200,
        apn_validations={}
    )
    
    v1 = evaluator.evaluate(t1, "shasta", vendor)
    p1 = state_tracker.ingest(v1)
    print("RUN 1: Perfect Execution")
    DashboardAggregator.print_dashboard(v1, p1)
    print("\n")
    
    # Run 2: Hard Halt (Network Error)
    t2 = RuntimeTelemetry(
        execution_graph_id="g2",
        step_results=[
            ExecutionResult("S1", "SUCCESS", {}, 100, None, None),
            ExecutionResult("S2", "FAILURE", {}, 500, "NETWORK_ERROR", None)
        ],
        strategy_planned="HTTP_ONLY",
        strategy_observed="HTTP_ONLY",
        failure_step="S2",
        failure_context={"error_type": "NETWORK_ERROR"},
        total_latency_ms=600,
        apn_validations={}
    )
    
    v2 = evaluator.evaluate(t2, "shasta", vendor)
    p2 = state_tracker.ingest(v2)
    print("RUN 2: Hard Halt (Network Error)")
    DashboardAggregator.print_dashboard(v2, p2)
    print("\n")
    
    # Run 3: Another Hard Halt (Network Error) showing drift
    v3 = evaluator.evaluate(t2, "shasta", vendor)
    p3 = state_tracker.ingest(v3)
    print("RUN 3: Hard Halt (Network Error) [EMA Drift]")
    DashboardAggregator.print_dashboard(v3, p3)

if __name__ == "__main__":
    test_cars2_pipeline()
