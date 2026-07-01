import json
from aql1 import AcquisitionQualityLens
from vpr2 import VPR2Interpreter
from vpr3 import VPR3Compiler
from eer1 import ExecutionRuntime
from cars2 import StatelessEvaluator
from cars2_state import HealthEstimator
from constraint_solver import ConstraintSolver
from calibration_sweep import simulate_aql_diagnostic, load_registry

def run_closed_loop_sweep():
    registry = load_registry()
    
    # Init Pipeline Layers
    vpr2 = VPR2Interpreter()
    vpr3 = VPR3Compiler()
    eer1 = ExecutionRuntime()
    cars2_eval = StatelessEvaluator()
    cars2_state = HealthEstimator(alpha=0.6) # Aggressive alpha to show fast drift
    
    # To demonstrate the FME entropy lock, we will run multiple sweeps across the counties
    # and simulate failing network errors for LA repeatedly.
    
    print("==================================================")
    print("  PHASE 2.16: CLOSED-LOOP STRESS TEST")
    print("==================================================")
    
    for iteration in range(1, 5):
        print(f"\n--- SWEEP ITERATION {iteration} ---")
        
        for county, data in registry.items():
            if county != "los_angeles": continue # We will just focus on Los Angeles to show entropy lock
            
            print(f"\nEvaluating: {county.upper()} ({data['vendor_class']})")
            
            # Step 0: Check constraints (CARS-3) before execution
            profile = cars2_state.get_profile(data["vendor_class"])
            if iteration == 4 and profile:
                profile.ema_fme = 0.95 # Artificially simulate massive entropy spike before solving constraints
                
            acv = None
            if profile:
                # We need a dummy eval vector just to seed the solver, or we can just use the previous FME/VSI
                # In a real system, the solver takes the aggregated profile and the last eval vector.
                # For our pure function, we'll pass a dummy SER to see the VSI/FME bounds.
                from cars2 import EvaluationVector
                dummy_eval = EvaluationVector("dummy", county, data["vendor_class"], 1.0, 1.0, 0.0, 0.0, 0.0)
                acv = ConstraintSolver.solve(dummy_eval, profile)
                print(f"  [CARS-3] Output Constraint: Mode={acv.execution_mode.value}, Diagnostic={acv.diagnostic_reason}")
            
            # 1. AQL-1 (Simulate Baseline Failure - LA WAF block)
            aql_diag = simulate_aql_diagnostic(county, data["vendor_class"], data["target_url"])
            
            # 2. VPR-2 (Interpretation + ACV bounds)
            vpr2_decision = vpr2.interpret(county, aql_diag, acv=acv)
            print(f"  [VPR-2] Decided Strategy: {vpr2_decision.acquisition_strategy.value}")
            
            # 3. VPR-3 (Compilation)
            vpr3_graph = vpr3.compile(vpr2_decision)
            
            # 4. EER-1 (Execution + ACV bounds)
            telemetry = eer1.execute_graph(vpr3_graph, acv=acv)
            
            if telemetry.strategy_observed == "OBSERVATION_ONLY":
                print("  [EER-1] HALTED: ACV forced system into OBSERVATION_ONLY.")
            else:
                print(f"  [EER-1] Executed. Hard Halt? {'YES' if telemetry.failure_step else 'NO'}")
            
            # 5. CARS-2 (Evaluation & State Tracking)
            eval_vec = cars2_eval.evaluate(telemetry, county, vpr2_decision.vendor_class.value)
            profile = cars2_state.ingest(eval_vec)
            
            print(f"  [CARS-2] Stateful EMA FME: {profile.ema_fme:.2f} | EMA VSI: {profile.ema_vsi:.2f}")

if __name__ == "__main__":
    run_closed_loop_sweep()
