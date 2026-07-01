import hashlib
from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class DeterministicExecutionTrace:
    """
    DDL-1 Trace: The scientific ledger proving identical physical execution.
    Contains the exact payload fired, the precise temporal window, and the raw envelope received.
    """
    step_id: str
    actuator_type: str
    
    # Exact Request Payload
    req_method: str
    req_url: str
    req_headers: dict
    req_payload: Optional[dict]
    req_timeout_ms: int
    
    # Timing Window
    time_start_unix: float
    time_end_unix: float
    duration_ms: int
    
    # Raw Response Envelope
    res_status: Optional[int]
    res_error_type: Optional[str]
    res_body_hash: str # SHA-256 of the raw body payload (to keep logs small but deterministic)
    
    def compute_signature(self) -> str:
        # A hash representing the complete physical event
        payload = f"{self.step_id}|{self.actuator_type}|{self.req_method}|{self.req_url}|{self.duration_ms}|{self.res_status}|{self.res_error_type}|{self.res_body_hash}"
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()
