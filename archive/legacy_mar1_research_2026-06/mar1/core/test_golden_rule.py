import os
import shutil
import json
from mar1.core.mar1_runtime import MAR1Runtime
from mar1.ob1.mar1_ob1_service import initialize_ob1, shutdown_ob1

def run_golden_rule_check():
    """
    Validates the Golden Rule Invariant:
    ∀ t:  ∂MAR1_decision(t) / ∂OB1_output(t-1) = 0
    MAR-1 decisions at time t must not change if OB-1 logs from time t-1 are altered or missing.
    """
    print("Running Golden Rule Invariant Check...\n")
    
    # ---------------------------------------------------------
    # STEP A: Run MAR-1 with OB-1 fully enabled and logging
    # ---------------------------------------------------------
    print("STEP A: Executing MAR-1 with OB-1 ACTIVE")
    test_log_dir = "logs/golden_rule_logs"
    if os.path.exists(test_log_dir):
        shutil.rmtree(test_log_dir)
        
    initialize_ob1(log_dir=test_log_dir, wal_mode="SAFE")
    runtime_a = MAR1Runtime()
    
    trace_a = []
    for i in range(50):
        # Deterministic inputs
        result = runtime_a.execute_cycle({"doc_id": i, "field": "test"})
        trace_a.append(result)
        
    shutdown_ob1()
    print(" -> Completed 50 cycles with logging.")
    
    # ---------------------------------------------------------
    # STEP B: Run MAR-1 with OB-1 completely disabled
    # ---------------------------------------------------------
    print("STEP B: Executing MAR-1 with OB-1 DISABLED (simulated crash)")
    runtime_b = MAR1Runtime()
    
    trace_b = []
    for i in range(50):
        result = runtime_b.execute_cycle({"doc_id": i, "field": "test"})
        trace_b.append(result)
        
    print(" -> Completed 50 cycles without logging.")
    
    # ---------------------------------------------------------
    # STEP C: Compare
    # ---------------------------------------------------------
    print("\nSTEP C: Comparing decision traces...")
    is_match = (trace_a == trace_b)
    
    if is_match:
        print("[SUCCESS] Golden Rule Invariant holds: OB-1 is not a hidden control input.")
    else:
        print("[FAIL] Golden Rule Violation: Feedback leakage detected.")

if __name__ == "__main__":
    run_golden_rule_check()
