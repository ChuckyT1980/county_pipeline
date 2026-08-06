import time
import uuid
import hashlib
import numpy as np
from typing import Dict, Any, Optional

from mar1.core.mar1_decision import (
    MAR1State, MAR1Decision, 
    evaluate_policy
)
from mar1.ob1.mar1_event import OB1Event
from mar1.ob1.mar1_ob1_service import emit_observation
from mar1.core.mar1_faults import Snapshot

class MAR1Runtime:
    """
    MAR-1 Control Plane.
    Executes the deterministic reactive policy.
    """
    def __init__(self):
        self.cycle_count = 0
        self.prev_E = 1.0
        self.prev_R = 0.0
        
    def reset(self):
        self.cycle_count = 0
        self.prev_E = 1.0
        self.prev_R = 0.0
        
    def execute(self, snapshot: Snapshot) -> dict:
        self.cycle_count += 1
        
        # 1. State initialization from Snapshot
        observability = len(snapshot.ob1_stream) / 50.0 if snapshot.ob1_stream is not None else 0.0
        observability = min(1.0, max(0.0, observability))
        
        latency_variance = 0.0
        if snapshot.wal_view and len(snapshot.wal_view) > 1:
            timestamps = [e.timestamp for e in snapshot.wal_view]
            diffs = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
            var = float(np.var(diffs))
            # normalized to 0..1 (sigma=200 -> var=80000 approx)
            latency_variance = min(1.0, var / 80000.0)
        elif not snapshot.wal_view:
            latency_variance = 1.0
            
        residual_gap = 0.05
        if snapshot.ob1_stream:
            avg_p = sum(e.pressure_scalar for e in snapshot.ob1_stream) / len(snapshot.ob1_stream)
            # Smoothly degrade based on semantic drift severity
            if avg_p > 0.5:
                mapped_gap = (avg_p - 0.5) / 10.0
                residual_gap = max(0.05, min(1.0, mapped_gap))
                
        state = MAR1State(
            observability=observability,
            latency_variance=latency_variance,
            residual_gap=residual_gap,
            prev_E=self.prev_E,
            prev_R=self.prev_R
        )
        
        # 2. Execute reactive policy
        decision = evaluate_policy(state)
        
        # Update memory
        self.prev_E = decision.E
        self.prev_R = decision.R
        
        # 3. Build observation payload
        event = self._build_observation_payload(state, decision, snapshot)
        
        # 4. Emit observation
        emit_observation(event, mode="ASYNC")
        
        # 5. Return CFIT-1 trace
        return {
            "decision_state": event.decision_state,
            "P_t": event.pressure_scalar,
            "E_t": event.elasticity_score,
            "R_t": event.risk_score,
            "failure_flags": {
                "timeout": event.timeout_flag,
                "schema_mismatch": event.schema_mismatch_flag,
                "drift_detected": event.drift_detected_flag,
                "consistency": event.consistency_harness_flag
            },
            "timestamp": event.timestamp
        }
        
    def _build_observation_payload(self, state: MAR1State, decision: MAR1Decision, snapshot: Snapshot) -> OB1Event:
        t_snapshot = time.time()
        
        event_id = str(uuid.uuid4())
        raw_input = snapshot.dom if snapshot.dom else {}
        env_hash = hashlib.sha256(str(raw_input).encode()).hexdigest()
        
        return OB1Event(
            event_id=event_id,
            timestamp=t_snapshot,
            execution_cycle=self.cycle_count,
            request_payload=raw_input,
            environment_snapshot_hash=env_hash,
            session_context_hash=None,
            decision_state=decision.state,
            pressure_scalar=decision.P,
            elasticity_score=decision.E,
            risk_score=decision.R,
            selected_batch_key=("default_risk", "stable", "example.com"),
            response_payload={},
            response_validity_flag=True,
            timeout_flag=False,
            schema_mismatch_flag=False,
            drift_detected_flag=False,
            consistency_harness_flag=False
        )
