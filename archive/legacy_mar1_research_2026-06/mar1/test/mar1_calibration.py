import time
from typing import List, Dict, Any
from mar1.core.mar1_runtime import MAR1Runtime
from mar1.core.mar1_faults import FaultDescriptor, Snapshot, apply_fault
from mar1.ob1.mar1_ob1_service import initialize_ob1, shutdown_ob1
from mar1.ob1.mar1_event import OB1Event

def generate_dummy_snapshot(cycle: int) -> Snapshot:
    dummy_ob1_stream = [
        OB1Event(
            event_id=f"evt_{i}", timestamp=time.time() + i, execution_cycle=i, request_payload={},
            environment_snapshot_hash="h", session_context_hash=None, decision_state="NORMAL",
            pressure_scalar=0.5, elasticity_score=0.9, risk_score=0.1, selected_batch_key=("a","b","c"),
            response_payload={}, response_validity_flag=True, timeout_flag=False, schema_mismatch_flag=False,
            drift_detected_flag=False, consistency_harness_flag=False
        ) for i in range(50)
    ]
    return Snapshot(dom={"cycle": cycle}, ob1_stream=list(dummy_ob1_stream), wal_view=list(dummy_ob1_stream))

def run_class_d_sweep():
    print("=== CLASS D RESIDUAL SWEEP ===")
    runtime = MAR1Runtime()
    for scale in [1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]:
        runtime.reset()
        final_R, final_P, final_state = 0, 0, "NORMAL"
        for t in range(20):
            snap = generate_dummy_snapshot(t)
            faulted = apply_fault(snap, FaultDescriptor(mode="CLASS_D", parameters={"scale_factor": scale}))
            decision = runtime.execute(faulted)
            final_R = decision['R_t']
            final_P = decision['P_t']
            final_state = decision['decision_state']
        print(f"Scale: {scale:>4.1f} | R: {final_R:.4f} | P: {final_P:.4f} | State: {final_state}")
    print()

def run_class_b_sweep():
    print("=== CLASS B ELASTICITY SWEEP ===")
    runtime = MAR1Runtime()
    for drop_rate in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        runtime.reset()
        final_E, final_P, final_state = 0, 0, "NORMAL"
        for t in range(30):
            snap = generate_dummy_snapshot(t)
            faulted = apply_fault(snap, FaultDescriptor(mode="CLASS_B", parameters={"drop_rate": drop_rate}))
            decision = runtime.execute(faulted)
            final_E = decision['E_t']
            final_P = decision['P_t']
            final_state = decision['decision_state']
        print(f"Drop Rate: {drop_rate:.1f} | E: {final_E:.4f} | P: {final_P:.4f} | State: {final_state}")
    print()

def run_hysteresis_check():
    print("=== HYSTERESIS CHECK ===")
    runtime = MAR1Runtime()
    runtime.reset()
    
    trace = []
    
    for t in range(10): # Healthy
        snap = generate_dummy_snapshot(t)
        trace.append(runtime.execute(snap)['decision_state'])
        
    for t in range(10): # Corrupt (Class A complete loss)
        snap = generate_dummy_snapshot(t+10)
        faulted = apply_fault(snap, FaultDescriptor(mode="CLASS_A"))
        trace.append(runtime.execute(faulted)['decision_state'])
        
    for t in range(10): # Healthy
        snap = generate_dummy_snapshot(t+20)
        trace.append(runtime.execute(snap)['decision_state'])
        
    print("Trace Output:")
    print(" | ".join(trace))
    print()

if __name__ == "__main__":
    initialize_ob1(log_dir="logs/cfit1_calib", wal_mode="SAFE")
    run_class_d_sweep()
    run_class_b_sweep()
    run_hysteresis_check()
    shutdown_ob1()
