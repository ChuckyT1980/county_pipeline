import math
import time
import numpy as np
from dataclasses import dataclass
from mar1.core.mar1_runtime import MAR1Runtime
from mar1.core.mar1_faults import FaultDescriptor, Snapshot, apply_fault
from mar1.ob1.mar1_ob1_service import initialize_ob1, shutdown_ob1
from mar1.ob1.mar1_event import OB1Event

@dataclass
class FaultScenario:
    name: str
    fault_class: str
    parameters: dict

SCENARIOS = [
    FaultScenario("baseline", "NONE", {}),
    FaultScenario("class_a", "CLASS_A", {}),
    FaultScenario("class_b", "CLASS_B", {"drop_rate": 0.5}),
    FaultScenario("class_c", "CLASS_C", {"jitter_sigma": 200}),
    FaultScenario("class_d", "CLASS_D", {"scale_factor": 100}),
    FaultScenario("mixed", "MIXED", {"a": True, "b": True, "c": True, "d": True})
]

EXECUTION_STEPS = 50

class CFIT1Orchestrator:
    def __init__(self, mar1_runtime, apply_fault_fn):
        self.mar1 = mar1_runtime
        self.apply_fault = apply_fault_fn
        self.results = {}
        self.baseline_mu = None
        self.baseline_sigma = None

    def _extract_features(self, trace):
        if not trace:
            return np.zeros(10)
            
        P_t = [x['P_t'] for x in trace]
        E_t = [x['E_t'] for x in trace]
        R_t = [x['R_t'] for x in trace]
        states = [x['decision_state'] for x in trace]
        
        counts = {"SAFE_HALT": 0, "NORMAL": 0, "CONSERVATIVE": 0}
        for s in states:
            if s in counts:
                counts[s] += 1
                
        entropy = 0
        state_counts = {}
        for s in states:
            state_counts[s] = state_counts.get(s, 0) + 1
        for c in state_counts.values():
            p = c / len(states)
            entropy -= p * math.log2(p)
            
        phi = [
            np.mean(P_t) if P_t else 0.0, np.var(P_t) if len(P_t)>1 else 0.0,
            np.mean(E_t) if E_t else 0.0, np.var(E_t) if len(E_t)>1 else 0.0,
            np.mean(R_t) if R_t else 0.0, np.var(R_t) if len(R_t)>1 else 0.0,
            counts["SAFE_HALT"] / len(states),
            counts["NORMAL"] / len(states),
            counts["CONSERVATIVE"] / len(states),
            entropy
        ]
        return np.array(phi, dtype=float)

    def compute_S(self, clean_trace, fault_trace, lambd=1.5):
        phi_clean = self._extract_features(clean_trace)
        phi_fault = self._extract_features(fault_trace)
        
        eps = 1e-6
        phi_clean_norm = (phi_clean - self.baseline_mu) / (self.baseline_sigma + eps)
        phi_fault_norm = (phi_fault - self.baseline_mu) / (self.baseline_sigma + eps)
        
        D = np.linalg.norm(phi_clean_norm - phi_fault_norm)
        return math.exp(-lambd * D)

    def run(self):
        clean_trace = self._run_scenario(SCENARIOS[0])
        phi_clean = self._extract_features(clean_trace)
        
        self.baseline_mu = phi_clean
        # Use a small non-zero sigma to prevent division by zero on static stubs
        self.baseline_sigma = np.ones_like(phi_clean) * 0.1
        
        from mar1.test.mar1_failure_profiler import profile_failure
        
        self.results["baseline"] = {
            "trace": clean_trace, 
            "stability": 1.0,
            "profile": profile_failure(clean_trace, clean_trace, 1.0)
        }
        
        for scenario in SCENARIOS[1:]:
            faulted_trace = self._run_scenario(scenario)
            S = self.compute_S(clean_trace, faulted_trace)
            prof = profile_failure(clean_trace, faulted_trace, S)
            self.results[scenario.name] = {
                "trace": faulted_trace,
                "stability": round(S, 4),
                "profile": prof
            }
            
        return self.results

    def _run_scenario(self, scenario):
        trace = []
        self.mar1.reset()
        
        # Populate dummy events for fault injection to operate on
        dummy_ob1_stream = [
            OB1Event(
                event_id=f"evt_{i}", timestamp=time.time(), execution_cycle=i, request_payload={},
                environment_snapshot_hash="h", session_context_hash=None, decision_state="NORMAL",
                pressure_scalar=0.5, elasticity_score=0.9, risk_score=0.1, selected_batch_key=("a","b","c"),
                response_payload={}, response_validity_flag=True, timeout_flag=False, schema_mismatch_flag=False,
                drift_detected_flag=False, consistency_harness_flag=False
            ) for i in range(EXECUTION_STEPS)
        ]
        
        for t in range(EXECUTION_STEPS):
            snapshot = Snapshot(dom={"cycle": t}, ob1_stream=list(dummy_ob1_stream), wal_view=list(dummy_ob1_stream))
            
            faulted_snapshot = self.apply_fault(
                snapshot, 
                FaultDescriptor(mode=scenario.fault_class, parameters=scenario.parameters)
            )
            
            decision = self.mar1.execute(faulted_snapshot)
            trace.append(decision)
            
        return trace

if __name__ == "__main__":
    initialize_ob1(log_dir="logs/cfit1_logs", wal_mode="SAFE")
    runtime = MAR1Runtime()
    orchestrator = CFIT1Orchestrator(runtime, apply_fault)
    
    print("Running CFIT-1 Fault Injection Harness...\n")
    results = orchestrator.run()
    
    print("=== CFIT-1 Stability Results ===")
    for name, data in results.items():
        prof = data['profile']
        print(f"Scenario {name.upper():<10} -> S: {data['stability']:.4f} | Driver: {prof.dominant_driver:<4} | Class: {prof.classification}")
        
    shutdown_ob1()
