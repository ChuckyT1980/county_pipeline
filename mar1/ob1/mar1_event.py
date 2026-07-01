import json
from dataclasses import dataclass, asdict
from typing import Optional, Tuple

@dataclass(frozen=True)
class OB1Event:
    event_id: str
    timestamp: float
    execution_cycle: int

    request_payload: dict
    environment_snapshot_hash: str
    session_context_hash: Optional[str]

    decision_state: str  # ENUM (NORMAL, CONSERVATIVE, PROBE_ONLY, SAFE_HALT)

    pressure_scalar: float
    elasticity_score: float
    risk_score: float

    selected_batch_key: Tuple[str, str, str]

    response_payload: dict
    response_validity_flag: bool

    timeout_flag: bool
    schema_mismatch_flag: bool
    drift_detected_flag: bool
    consistency_harness_flag: bool

    def to_json(self) -> str:
        # Strictly enforces JSONL format: 1 event per line, no pretty-printing
        return json.dumps(asdict(self), separators=(',', ':'))
