import json
import os
import math
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from eer1_schemas import SessionContext, RuntimeTelemetry
from dispatchers_live import LiveDispatcher
from cva1 import ConstraintViolationAuditor
from cars2 import StatelessEvaluator
from cars2_state import HealthEstimator
from cars3_schemas import ActionConstraintVector, ExecutionMode

def calculate_distance(v1: dict, v2: dict) -> float:
    # Euclidean distance over EFS, VSI, FME
    return math.sqrt(
        (v1["EFS"] - v2["EFS"])**2 +
        (v1["VSI"] - v2["VSI"])**2 +
        (v1["FME"] - v2["FME"])**2
    )

def execute_sweep():
    print("--- PHASE 3.4: MULTI-COUNTY ENTROPY PROFILING ---")
    
    with open("data/registry/vpr_registry.json", "r") as f:
        registry = json.load(f)["counties"]
        
    dispatcher = LiveDispatcher()
    evaluator = StatelessEvaluator()
    
    # Layer A: Raw Observation Tensor
    profiles = []
    
    # Strictly freeze control system
    observability_acv = ActionConstraintVector(
        allowed_strategies=["HTTP_ONLY"],
        retry_budget=0,
        escalation_threshold=1.0,
        vendor_class_lock=None,
        execution_mode=ExecutionMode.OBSERVATION_ONLY,
        confidence_floor=0.9,
        entropy_cap=1.0,
        diagnostic_reason="PHASE_3.4_OBSERVABILITY_SWEEP",
        allow_recompile=False,
        allow_strategy_switch=False,
        allow_retry=False,
        allow_actuator_fallback=False
    )

    for county, data in registry.items():
        print(f"\nProbing {county} ({data['vendor_class']})...")
        target_url = data["target_url"]
        
        # 1. Neutral GET instruction
        step = ExecutionStep("S1", StepType.HTTP_REQUEST, target_url, {}, 5000, "NONE", ["raw_html"])
        graph = ExecutionGraph(county, data["vendor_class"], "HTTP_ONLY", [step], [], ["raw_html"])
        
        # 2. Dumb Actuation
        session = SessionContext()
        result = dispatcher.execute(step, session)
        
        # 3. Telemetry wrapping
        telemetry = RuntimeTelemetry(
            execution_graph_id=f"sweep_{county}",
            step_results=[result],
            strategy_planned="HTTP_ONLY",
            strategy_observed="HTTP_ONLY",
            failure_step=step.id if result.status == "FAILURE" else None,
            total_latency_ms=result.latency_ms,
            apn_validations={},
            failure_context={"diagnostic": "GET Request Completed", "error_type": result.error_type} if result.status == "FAILURE" else None
        )
        
        # 4. CVA-1 Classification
        # Mock raw payload for CVA-1 schema evaluation (we are only testing HTTP layer entropy here)
        raw_responses = [{"mock_is_captcha": False, "mock_is_redesign": False}]
        violation_report = ConstraintViolationAuditor.verify(telemetry, graph, observability_acv, raw_responses)
        
        # 5. CARS-2 Extraction
        eval_vector = evaluator.evaluate(telemetry, county, data["vendor_class"])
        
        # We don't ingest into EMA, we just want the instantaneous vector
        v = {
            "county": county,
            "vendor_class": data["vendor_class"],
            "vector": {
                "EFS": round(eval_vector.efs, 2),
                "VSI": round(eval_vector.vsi_contrib, 2),
                "FME": round(eval_vector.fme_contrib, 2),
                "cva_class": violation_report.violation_type.value if result.status == "SUCCESS" else (result.error_type.value if result.error_type else "UNKNOWN"),
                "latency_ms": result.latency_ms
            }
        }
        profiles.append(v)
        
        print(f"  -> Vector: {v['vector']}")

    # Ensure output dir
    os.makedirs("data/telemetry", exist_ok=True)

    # 6. Layer B: Derived Geometry (Distance Matrix)
    distance_matrix = {}
    for i, p1 in enumerate(profiles):
        for j, p2 in enumerate(profiles):
            if i < j:
                dist = calculate_distance(p1["vector"], p2["vector"])
                distance_matrix[f"{p1['county']} <-> {p2['county']}"] = round(dist, 2)
                
    # Basic clustering bucketing based on EFS, VSI, FME signatures
    clusters = {
        "HARD_BLOCKED": [],
        "STABLE_HTTP": [],
        "SOFT_DEGRADED": [],
        "UNKNOWN": []
    }
    
    for p in profiles:
        v = p["vector"]
        if v["VSI"] == 1.0 and v["FME"] <= 0.5:
            clusters["STABLE_HTTP"].append(p["county"])
        elif v["VSI"] == 0.0 and v["FME"] >= 0.8:
            clusters["HARD_BLOCKED"].append(p["county"])
        elif v["VSI"] > 0.0 and v["FME"] > 0.5:
            clusters["SOFT_DEGRADED"].append(p["county"])
        else:
            clusters["UNKNOWN"].append(p["county"])

    # 7. Write Output Tensor
    output_tensor = {
        "layer_a_raw_vectors": profiles,
        "layer_b_geometry": {
            "pairwise_distances": distance_matrix,
            "signature_clusters": clusters
        }
    }
    
    with open("data/telemetry/entropy_profiles.json", "w") as f:
        json.dump(output_tensor, f, indent=2)
        
    print("\n--- SWEEP COMPLETE ---")
    print("Layer A & B outputs written to data/telemetry/entropy_profiles.json")
    print(f"Clusters discovered: {json.dumps(clusters, indent=2)}")

if __name__ == "__main__":
    execute_sweep()
