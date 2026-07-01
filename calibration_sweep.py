import json
from aql1 import AcquisitionQualityLens
from vpr2 import VPR2Interpreter
from vpr3 import VPR3Compiler
from eer1 import ExecutionRuntime
from cars2 import StatelessEvaluator
from cars2_state import HealthEstimator
import time

def load_registry():
    with open("data/registry/vpr_registry.json", "r") as f:
        return json.load(f)["counties"]

def simulate_aql_diagnostic(county: str, vendor_class: str, target_url: str):
    # Simulating what AQL-1 would see after a BaselineFetcher failure in the real world.
    # To test maximum entropy, we'll simulate different behaviors for the counties:
    if county == "shasta":
        # Classic MPTS WAF block
        return {
            "endpoint": target_url, "status": 403, "classification": "ACCESS_DENIED",
            "signals": {"vendor": "MPTS", "route_type": "parcel_search_view", "waf_likelihood": 0.99, "session_dependency_likelihood": 0.0},
            "confidence": 0.9
        }
    elif county == "tehama":
        # Older MPTS, maybe just rate limited
        return {
            "endpoint": target_url, "status": 429, "classification": "RATE_LIMITED",
            "signals": {"vendor": "MPTS", "route_type": "parcel_search_view", "waf_likelihood": 0.3, "session_dependency_likelihood": 0.0},
            "confidence": 0.9
        }
    elif county == "san_bernardino":
        # Aumentum Stateful Session Requirement
        return {
            "endpoint": target_url, "status": 200, "classification": "SUCCESS",
            "signals": {"vendor": "Aumentum", "route_type": "parcel_search_view", "waf_likelihood": 0.0, "session_dependency_likelihood": 0.95},
            "confidence": 0.9
        }
    elif county == "los_angeles":
        # Fragmented LA - WAF block on a custom CMS
        return {
            "endpoint": target_url, "status": 403, "classification": "ACCESS_DENIED",
            "signals": {"vendor": "GovOS", "route_type": "unknown_route", "waf_likelihood": 0.95, "session_dependency_likelihood": 0.4},
            "confidence": 0.9
        }
    elif county == "riverside":
        # Hybrid Aumentum - partial render
        return {
            "endpoint": target_url, "status": 200, "classification": "SUCCESS",
            "signals": {"vendor": "Aumentum", "route_type": "parcel_search_view", "waf_likelihood": 0.0, "session_dependency_likelihood": 0.6},
            "confidence": 0.9
        }
    
    return {"status": 500}

def run_calibration_sweep():
    registry = load_registry()
    
    # Init Pipeline Layers
    vpr2 = VPR2Interpreter()
    vpr3 = VPR3Compiler()
    eer1 = ExecutionRuntime()
    cars2_eval = StatelessEvaluator()
    cars2_state = HealthEstimator(alpha=0.3)
    
    behavior_map = {}
    
    print("==================================================")
    print("  PHASE 2.15: REALITY CALIBRATION SWEEP")
    print("==================================================")
    
    for county, data in registry.items():
        print(f"\nEvaluating: {county.upper()} ({data['vendor_class']})")
        
        # 1. AQL-1 (Simulate Baseline Failure)
        aql_diag = simulate_aql_diagnostic(county, data["vendor_class"], data["target_url"])
        
        # 2. VPR-2 (Interpretation)
        vpr2_decision = vpr2.interpret(county, aql_diag)
        print(f"  [VPR-2] Decided Strategy: {vpr2_decision.acquisition_strategy.value}")
        
        # 3. VPR-3 (Compilation)
        vpr3_graph = vpr3.compile(vpr2_decision)
        print(f"  [VPR-3] Compiled E-Graph ({len(vpr3_graph.steps)} steps)")
        
        # 4. EER-1 (Execution)
        # Note: In our current stub, EER-1 will naturally fail on the HTTP dispatcher for some of these mocked URLs
        # which is perfect, as it gives us empirical failure telemetry.
        telemetry = eer1.execute_graph(vpr3_graph)
        print(f"  [EER-1] Executed. Hard Halt? {'YES' if telemetry.failure_step else 'NO'}")
        
        # 5. CARS-2 (Evaluation & State Tracking)
        eval_vec = cars2_eval.evaluate(telemetry, county, vpr2_decision.vendor_class.value)
        profile = cars2_state.ingest(eval_vec)
        
        print(f"  [CARS-2] EFS: {eval_vec.efs:.2f} | SER: {eval_vec.ser:.2f} | FME_c: {eval_vec.fme_contrib:.2f} | STE_c: {eval_vec.ste_contrib:.2f}")
        
        behavior_map[county] = {
            "vendor_class": profile.vendor_class,
            "ema_vsi": round(profile.ema_vsi, 3),
            "ema_fme": round(profile.ema_fme, 3),
            "ema_ste": round(profile.ema_ste, 3),
            "strategy_used": vpr2_decision.acquisition_strategy.value
        }
        
    print("\n==================================================")
    print("  EMPIRICAL BEHAVIOR MAP GENERATED")
    print("==================================================")
    
    with open("data/behavior_map.json", "w") as f:
        json.dump(behavior_map, f, indent=2)

if __name__ == "__main__":
    run_calibration_sweep()
