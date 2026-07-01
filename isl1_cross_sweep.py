import json
import os
import math
from dispatchers_live import LiveDispatcher
from cva1 import ConstraintViolationAuditor
from cars2 import StatelessEvaluator
from cars3_schemas import ActionConstraintVector, ExecutionMode
from isl1_probes import ISLProbeGenerator
from eer1_schemas import RuntimeTelemetry

def jensen_shannon_divergence(p: list, q: list) -> float:
    def kl_divergence(p, q):
        return sum(p[i] * math.log2(p[i]/q[i]) if p[i] != 0 and q[i] != 0 else 0 for i in range(len(p)))
    
    m = [(p[i] + q[i]) / 2 for i in range(len(p))]
    return 0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m)

def get_class_index(cva_class: str) -> int:
    classes = ["NONE", "NETWORK_ERROR", "STEP_TIMEOUT", "SOFT_BLOCK_CAPTCHA", "PARTIAL_DOM_RENDER", "REDIRECT_CHAIN_OBSERVED", "SESSION_CHALLENGE", "UNKNOWN_FAILURE"]
    return classes.index(cva_class) if cva_class in classes else len(classes)-1

def build_distribution(classifications: list) -> list:
    dist = [0.0] * 8
    if not classifications: return dist
    for c in classifications:
        dist[get_class_index(c)] += 1.0
    return [x / len(classifications) for x in dist]

def run_isl1_sweep():
    print("--- PHASE 3.7: ISL-1 INSTRUMENT STRESS INJECTION SWEEP ---")
    
    with open("data/registry/vpr_registry.json", "r") as f:
        registry = json.load(f)["counties"]
        
    dispatcher = LiveDispatcher()
    evaluator = StatelessEvaluator()
    
    observability_acv = ActionConstraintVector(
        allowed_strategies=["HTTP_ONLY", "BROWSER_ONLY"],
        retry_budget=0,
        escalation_threshold=1.0,
        vendor_class_lock=None,
        execution_mode=ExecutionMode.OBSERVATION_ONLY,
        confidence_floor=0.9,
        entropy_cap=1.0,
        diagnostic_reason="PHASE_3.7_ISL1_SWEEP",
        allow_recompile=False,
        allow_strategy_switch=False,
        allow_retry=False,
        allow_actuator_fallback=False
    )

    # We exclusively target los_angeles for the phase transition boundary measurement
    target_county = "los_angeles"
    data = registry[target_county]
    target_url = data["target_url"]
    
    print(f"\n[Target] {target_county} ({data['vendor_class']})")
    
    probe_pairs = ISLProbeGenerator.generate_matrix(target_county, data["vendor_class"], target_url)
    
    divergence_topology = {}

    for pair in probe_pairs:
        print(f"\n  => Deploying {pair.type.value} Probe...")
        
        # 1. Execute HTTP Constraint
        res_h = dispatcher.execute(pair.http_graph.steps[0], pair.session)
        tel_h = RuntimeTelemetry(
            execution_graph_id=f"isl1_http_{target_county}_{pair.type.value}",
            step_results=[res_h],
            strategy_planned="HTTP_ONLY",
            strategy_observed="HTTP_ONLY",
            failure_step=pair.http_graph.steps[0].id if res_h.status == "FAILURE" else None,
            total_latency_ms=res_h.latency_ms,
            apn_validations={},
            failure_context={"diagnostic": "HTTP Probe", "error_type": res_h.error_type} if res_h.status == "FAILURE" else None
        )
        cva_h = ConstraintViolationAuditor.verify(tel_h, pair.http_graph, observability_acv, None)
        eval_h = evaluator.evaluate(tel_h, target_county, data["vendor_class"])
        class_h = cva_h.violation_type.value if res_h.status == "SUCCESS" else (res_h.error_type.value if res_h.error_type else "UNKNOWN_FAILURE")
        
        vec_h = {
            "EFS": round(eval_h.efs, 2), "VSI": round(eval_h.vsi_contrib, 2), "FME": round(eval_h.fme_contrib, 2), "CVA": class_h, "latency": res_h.latency_ms
        }
        
        # 2. Execute Playwright Constraint
        res_b = dispatcher.execute(pair.browser_graph.steps[0], pair.session)
        tel_b = RuntimeTelemetry(
            execution_graph_id=f"isl1_browser_{target_county}_{pair.type.value}",
            step_results=[res_b],
            strategy_planned="BROWSER_ONLY",
            strategy_observed="BROWSER_ONLY",
            failure_step=pair.browser_graph.steps[0].id if res_b.status == "FAILURE" else None,
            total_latency_ms=res_b.latency_ms,
            apn_validations={},
            failure_context={"diagnostic": "Playwright Probe", "error_type": res_b.error_type} if res_b.status == "FAILURE" else None
        )
        cva_b = ConstraintViolationAuditor.verify(tel_b, pair.browser_graph, observability_acv, None)
        eval_b = evaluator.evaluate(tel_b, target_county, data["vendor_class"])
        class_b = cva_b.violation_type.value if res_b.status == "SUCCESS" else (res_b.error_type.value if res_b.error_type else "UNKNOWN_FAILURE")
        
        vec_b = {
            "EFS": round(eval_b.efs, 2), "VSI": round(eval_b.vsi_contrib, 2), "FME": round(eval_b.fme_contrib, 2), "CVA": class_b, "latency": res_b.latency_ms
        }
        
        # 3. Compute Local Divergence
        p_h = build_distribution([class_h])
        p_b = build_distribution([class_b])
        ivd = round(jensen_shannon_divergence(p_h, p_b), 4)
        
        transition = f"{class_h} -> {class_b}"
        delta_vector = {
            "d_EFS": round(vec_b["EFS"] - vec_h["EFS"], 2),
            "d_VSI": round(vec_b["VSI"] - vec_h["VSI"], 2),
            "d_FME": round(vec_b["FME"] - vec_h["FME"], 2)
        }
        
        print(f"     HTTP: {class_h} (VSI: {vec_h['VSI']}, FME: {vec_h['FME']}, Latency: {vec_h['latency']}ms)")
        print(f"     Playwright: {class_b} (VSI: {vec_b['VSI']}, FME: {vec_b['FME']}, Latency: {vec_b['latency']}ms)")
        print(f"     Transition: {transition}")
        print(f"     IVD: {ivd}")
        
        divergence_topology[pair.type.value] = {
            "http_vector": vec_h,
            "playwright_vector": vec_b,
            "idf": {
                "delta_vector": delta_vector,
                "transition": transition,
                "ivd": ivd
            }
        }

    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/divergence_field_topology.json", "w") as f:
        json.dump({"los_angeles": divergence_topology}, f, indent=2)
        
    print("\n--- SWEEP COMPLETE ---")
    print("Divergence field topology written to data/telemetry/divergence_field_topology.json")

if __name__ == "__main__":
    run_isl1_sweep()
