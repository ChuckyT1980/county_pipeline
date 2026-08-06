import time
import random
from typing import Dict, Any

from mar1_mil import MAR1MeasurementIntegrityLayer
from mar1_constraints import MAR1GlobalConstraintMonitor
from mar1_tmdd import MAR1ThresholdModelDriftDetector
from mar1_ese import MAR1EpistemicStabilityEnvelope
from mar1_calibration import MAR1AutoCalibrationEngine
from mar1_decision import MAR1DecisionCore
from mar1_safety import MAR1SafetyKernel

from mar1_consistency import MAR1ConsistencyHarness

class MAR1Runtime:
    def __init__(self):
        self.safety = MAR1SafetyKernel()
        self.mil = MAR1MeasurementIntegrityLayer(probe_penalty_weight=1.2)
        self.constraints = MAR1GlobalConstraintMonitor(w1=1.0, w2=2.0, w3=0.5, w4=1.0, w5=0.5)
        self.tmdd = MAR1ThresholdModelDriftDetector()
        self.ese = MAR1EpistemicStabilityEnvelope(alpha=3.0)
        self.calibration = MAR1AutoCalibrationEngine()
        self.decision = MAR1DecisionCore()
        self.consistency = MAR1ConsistencyHarness()
        
        self.static_policy_mode = False
        
        # Sim State
        self.prev_mil_trust_avg = 1.0
        self.prev_tmdd_score = 0.0
        
    def dispatch_cycle(self, env_state: Dict[str, Any]):
        print("\n--- MAR-1 Dispatch Cycle ---")
        
        # 1. Reality Interface Lock
        if not self.safety.evaluate_execution_boundary(
                env_state["schema_hash"], 
                env_state["expected_hash"], 
                env_state["async_mismatch_rate"]):
            print("[CFV-6] STRICT ABORT: Reality boundary violated (Snapshot/Temporal drift).")
            return
            
        # 2. Measurement Integrity Check (MIL-1)
        trusted_tensor = self.mil.compute_trusted_tensor(
            raw_signals=env_state["raw_metrics"],
            signal_metadata=env_state["signal_meta"],
            probe_success_rate=env_state["probe_success_rate"]
        )
        
        avg_mil_trust = sum([meta["c"] - 0.5*meta["v"] - 0.8*meta["a"] for meta in env_state["signal_meta"].values()]) / max(1, len(env_state["signal_meta"]))
        avg_mil_trust = max(0.1, min(1.0, avg_mil_trust)) # Clamp
        
        # 3. Constraint Monitor
        p_t = self.constraints.compute_pressure(trusted_tensor)
        print(f"[Constraints] Base Pressure P(t): {p_t:.4f}")
        
        # 4. Calibration & TMDD
        theta_1, theta_2, theta_3 = self.calibration.get_thresholds()
        
        p_hat = p_t * 0.9 
        l_cal = self.tmdd.compute_calibration_loss(p_t, p_hat)
        l_real = self.tmdd.compute_outcome_loss(p_t, theta_3, failed=env_state["actual_failure"])
        
        var_p = 0.05 
        tmdd_score = self.tmdd.compute_tmdd(l_cal, l_real, var_p)
        print(f"[TMDD] Model Divergence Score: {tmdd_score:.4f}")
        
        # 5. Epistemic Stability Envelope (ESE)
        ese_t = self.ese.compute_ese(avg_mil_trust, tmdd_score)
        print(f"[ESE] Disagreement Gating Field: {ese_t:.4f}")
        
        mil_vol = abs(avg_mil_trust - self.prev_mil_trust_avg)
        tmdd_vol = abs(tmdd_score - self.prev_tmdd_score)
        
        if ese_t < 0.8: # Disagreement is high
            print(">> ESE COLLAPSE DETECTED. Diagnosing epistemic state...")
            k_coh = env_state.get("sim_directional_coherence", 0.0)
            m_drift = env_state.get("sim_monotonic_drift", 0.0)
            
            shape = self.ese.classify_collapse(mil_vol, tmdd_vol, k_coh, m_drift)
            print(f">> Diagnosis: {shape}")
            
            if shape in ["SENSOR_CORRUPTION", "COUPLED_FAILURE"]:
                print(">> FREEZING LEARNING. ENTERING SAFE STATIC POLICY MODE.")
                self.static_policy_mode = True
        
        self.prev_mil_trust_avg = avg_mil_trust
        self.prev_tmdd_score = tmdd_score
        
        # 6. Pressure Dampening
        p_prime = self.ese.apply_dampening(p_t, ese_t)
        print(f"[ESE] Dampened Action Pressure P'(t): {p_prime:.4f}")
        
        # 7. Blind Consistency Test Harness
        r_t = self.consistency.compute_residual_coherence_gap(
            env_state.get("o1_extracted", {}),
            env_state.get("o2_shadow_reconstruction", {})
        )
        if r_t > 0.3:
            print(f"[Consistency] Residual Coherence Gap R(t) Spike: {r_t:.4f}")
            
        # 8. Action Selection & Energy-Modulated Extraction
        policy = self.decision.determine_policy(p_prime, theta_1, theta_2, theta_3)
        
        # Calculate u(t)
        u_0 = 1.0
        e_t = env_state["raw_metrics"].get("E", 1.0)
        c_t = avg_mil_trust
        u_t = self.decision.compute_extraction_aggressiveness(u_0, r_t, e_t, c_t, alpha=5.0)
        
        dispatch_rules = self.decision.execute_policy(policy, u_t)
        print(f"[ARC-1] Policy: {policy} | Aggressiveness u(t): {u_t:.4f} | Dispatch: {dispatch_rules}")
        
        # 9. Post-Execution Calibration
        if not self.static_policy_mode:
            outcome = "success" if not env_state["actual_failure"] else "fail"
            cost = p_prime * 10.0 
            self.calibration.add_observation(p_prime, outcome, cost)
            self.calibration.compute_adaptive_thresholds()
            print(f"[Calibration] Updated Thresholds: theta_1={self.calibration.theta_1:.2f}, theta_2={self.calibration.theta_2:.2f}, theta_3={self.calibration.theta_3:.2f}")
        else:
            print("[Calibration] Updates frozen due to Static Policy Mode.")

def run_simulation():
    mar1 = MAR1Runtime()
    
    for _ in range(20):
        mar1.calibration.add_observation(random.uniform(0.1, 0.4), "success", 1.0)
    mar1.calibration.compute_adaptive_thresholds()
    
    print("=========================================")
    print("SCENARIO 1: Nominal Execution (Clean)")
    print("=========================================")
    env_nominal = {
        "schema_hash": "A1", "expected_hash": "A1", "async_mismatch_rate": 0.0,
        "raw_metrics": {"E": 0.9, "SCR": 0.05, "G_norm": 0.1, "R_ERM": 0.1},
        "signal_meta": {"E": {"c": 1.0, "v": 0.05, "d": 0.0, "a": 0.0}},
        "probe_success_rate": 1.0,
        "actual_failure": False,
        "sim_directional_coherence": 0.0, "sim_monotonic_drift": 0.0,
        "o1_extracted": {"internal_coherence": 1.0},
        "o2_shadow_reconstruction": {"expected_coherence": 0.95}
    }
    mar1.dispatch_cycle(env_nominal)
    
    print("\n=========================================")
    print("SCENARIO 2: Measurement Integrity Failure (Sensor Corruption)")
    print("=========================================")
    env_sensor_attack = {
        "schema_hash": "A1", "expected_hash": "A1", "async_mismatch_rate": 0.0,
        "raw_metrics": {"E": 0.9, "SCR": 0.0}, 
        "signal_meta": {"E": {"c": 0.2, "v": 0.9, "d": 0.8, "a": 0.9}}, 
        "probe_success_rate": 0.3, 
        "actual_failure": True,
        "sim_directional_coherence": 0.1, "sim_monotonic_drift": -0.1,
        "o1_extracted": {"internal_coherence": 1.0},
        "o2_shadow_reconstruction": {"expected_coherence": 1.0}
    }
    mar1.dispatch_cycle(env_sensor_attack)
    
    print("\n=========================================")
    print("SCENARIO 3: Internal Model Hallucination (False ESE Trigger)")
    print("=========================================")
    mar1.static_policy_mode = False 
    env_hallucination = {
        "schema_hash": "A1", "expected_hash": "A1", "async_mismatch_rate": 0.0,
        "raw_metrics": {"E": 0.8, "SCR": 0.1, "G_norm": 0.2, "R_ERM": 0.1},
        "signal_meta": {"E": {"c": 0.9, "v": 0.1, "d": 0.1, "a": 0.1}}, 
        "probe_success_rate": 0.95, 
        "actual_failure": True, 
        "sim_directional_coherence": -0.5, 
        "sim_monotonic_drift": 0.0,
        "o1_extracted": {"internal_coherence": 1.0},
        "o2_shadow_reconstruction": {"expected_coherence": 1.0}
    }
    mar1.dispatch_cycle(env_hallucination)

    print("\n=========================================")
    print("SCENARIO 4: Semantic Drift (The Missing Blindspot)")
    print("MIL, TMDD, ESE all report perfect stability. DOM is unchanged.")
    print("But internal consistency fails due to scrambled field meaning.")
    print("=========================================")
    mar1.static_policy_mode = False
    mar1.prev_mil_trust_avg = 1.0
    mar1.prev_tmdd_score = 0.0
    
    env_semantic_drift = {
        "schema_hash": "A1", "expected_hash": "A1", "async_mismatch_rate": 0.0,
        "raw_metrics": {"E": 1.0, "SCR": 0.0, "G_norm": 0.0, "R_ERM": 0.0}, # Perfectly healthy signals!
        "signal_meta": {"E": {"c": 1.0, "v": 0.0, "d": 0.0, "a": 0.0}}, # Extremely high trust
        "probe_success_rate": 1.0, # DOM sentinels succeed perfectly
        "actual_failure": False, # MAR-1 thinks it succeeded
        "sim_directional_coherence": 0.0, "sim_monotonic_drift": 0.0,
        # THE DIFFERENCE: Field consistency completely collapses
        "o1_extracted": {"internal_coherence": 0.1}, 
        "o2_shadow_reconstruction": {"expected_coherence": 1.0}
    }
    mar1.dispatch_cycle(env_semantic_drift)

if __name__ == "__main__":
    run_simulation()
