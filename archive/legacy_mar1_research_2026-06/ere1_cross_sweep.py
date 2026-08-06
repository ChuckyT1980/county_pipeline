import json
import os
import math
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from eer1_schemas import SessionContext, RuntimeTelemetry
from dispatchers_live import LiveDispatcher
from cva1 import ConstraintViolationAuditor
from cars2 import StatelessEvaluator
from cars3_schemas import ActionConstraintVector, ExecutionMode
from ere1_probes import ProbeGenerator

def jensen_shannon_divergence(p: list, q: list) -> float:
    # Approximate JSD for two discrete categorical distributions
    # Since our state space is discrete (CVA classifications), we'll do a simple entropy divergence
    # For now, we'll implement a deterministic JSD over a simplified 1D array of probabilities
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

def run_cross_instrument_sweep():
    print("--- PHASE 3.6: INSTRUMENT CAUSALITY SEPARATION LAYER ---")
    
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
        diagnostic_reason="PHASE_3.6_IDF_SWEEP",
        allow_recompile=False,
        allow_strategy_switch=False,
        allow_retry=False,
        allow_actuator_fallback=False
    )

    dual_topology_matrix = {}

    for county, data in registry.items():
        print(f"\n[Target] {county} ({data['vendor_class']})")
        target_url = data["target_url"]
        
        # --- 1. INSTRUMENT A: HTTP MANIFOLD (FULL MATRIX) ---
        http_signatures = {}
        http_classes = []
        http_baseline_vector = None
        
        probes = ProbeGenerator.generate_matrix(county, data["vendor_class"], target_url)
        for probe in probes:
            result = dispatcher.execute(probe.graph.steps[0], probe.session)
            
            telemetry = RuntimeTelemetry(
                execution_graph_id=f"ere1_http_{county}_{probe.type.value}",
                step_results=[result],
                strategy_planned="HTTP_ONLY",
                strategy_observed="HTTP_ONLY",
                failure_step=probe.graph.steps[0].id if result.status == "FAILURE" else None,
                total_latency_ms=result.latency_ms,
                apn_validations={},
                failure_context={"diagnostic": "HTTP Probe", "error_type": result.error_type} if result.status == "FAILURE" else None
            )
            
            violation_report = ConstraintViolationAuditor.verify(telemetry, probe.graph, observability_acv, None)
            eval_vector = evaluator.evaluate(telemetry, county, data["vendor_class"])
            
            classification = violation_report.violation_type.value if result.status == "SUCCESS" else (result.error_type.value if result.error_type else "UNKNOWN_FAILURE")
            http_classes.append(classification)
            
            signature = {
                "EFS": round(eval_vector.efs, 2),
                "VSI": round(eval_vector.vsi_contrib, 2),
                "FME": round(eval_vector.fme_contrib, 2),
                "CVA": classification
            }
            http_signatures[probe.type.value] = signature
            if probe.type.value == "BASELINE":
                http_baseline_vector = signature

        # --- 2. INSTRUMENT B: PLAYWRIGHT MANIFOLD (BASELINE ONLY) ---
        step_pw = ExecutionStep(f"{county}_pw", StepType.BROWSER_NAVIGATE, target_url, {}, 10000, "NONE", ["raw_html"])
        graph_pw = ExecutionGraph(county, data["vendor_class"], "BROWSER_ONLY", [step_pw], [], ["raw_html"])
        
        result_pw = dispatcher.execute(step_pw, SessionContext())
        telemetry_pw = RuntimeTelemetry(
            execution_graph_id=f"ere1_pw_{county}_BASELINE",
            step_results=[result_pw],
            strategy_planned="BROWSER_ONLY",
            strategy_observed="BROWSER_ONLY",
            failure_step=step_pw.id if result_pw.status == "FAILURE" else None,
            total_latency_ms=result_pw.latency_ms,
            apn_validations={},
            failure_context={"diagnostic": "Playwright Probe", "error_type": result_pw.error_type} if result_pw.status == "FAILURE" else None
        )
        violation_report_pw = ConstraintViolationAuditor.verify(telemetry_pw, graph_pw, observability_acv, None)
        eval_vector_pw = evaluator.evaluate(telemetry_pw, county, data["vendor_class"])
        
        classification_pw = violation_report_pw.violation_type.value if result_pw.status == "SUCCESS" else (result_pw.error_type.value if result_pw.error_type else "UNKNOWN_FAILURE")
        pw_baseline_vector = {
            "EFS": round(eval_vector_pw.efs, 2),
            "VSI": round(eval_vector_pw.vsi_contrib, 2),
            "FME": round(eval_vector_pw.fme_contrib, 2),
            "CVA": classification_pw
        }
        
        # --- 3. IDF: CAUSAL DIVERGENCE COMPUTATION ---
        p_http = build_distribution(http_classes)
        p_pw = build_distribution([classification_pw])
        
        ivd = round(jensen_shannon_divergence(p_http, p_pw), 4)
        
        delta_vector = {
            "d_EFS": round(pw_baseline_vector["EFS"] - http_baseline_vector["EFS"], 2),
            "d_VSI": round(pw_baseline_vector["VSI"] - http_baseline_vector["VSI"], 2),
            "d_FME": round(pw_baseline_vector["FME"] - http_baseline_vector["FME"], 2)
        }
        
        transition = f"{http_baseline_vector['CVA']} -> {pw_baseline_vector['CVA']}"
        
        print(f"  -> HTTP Baseline: {http_baseline_vector['CVA']}")
        print(f"  -> Playwright Baseline: {pw_baseline_vector['CVA']}")
        print(f"  -> Transition: {transition}")
        print(f"  -> IVD (Jensen-Shannon): {ivd}")
        
        dual_topology_matrix[county] = {
            "vendor_class": data["vendor_class"],
            "server_side_manifold_http": http_signatures,
            "client_side_manifold_playwright": {"BASELINE": pw_baseline_vector},
            "causal_divergence_idf": {
                "delta_vector": delta_vector,
                "transition": transition,
                "ivd": ivd
            }
        }

    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/dual_entropy_topology.json", "w") as f:
        json.dump(dual_topology_matrix, f, indent=2)
        
    print("\n--- SWEEP COMPLETE ---")
    print("Dual entropy topology written to data/telemetry/dual_entropy_topology.json")

if __name__ == "__main__":
    run_cross_instrument_sweep()
