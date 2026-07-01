from enum import Enum
from dataclasses import dataclass
from typing import Literal, Optional, Dict, Union

class ActuatorType(str, Enum):
    HTTP = "HTTP"
    PLAYWRIGHT = "PLAYWRIGHT"

class ErrorType(str, Enum):
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    SELECTOR_NOT_FOUND = "SELECTOR_NOT_FOUND"
    DNS_FAILURE = "DNS_FAILURE"
    WAF_BLOCK = "WAF_BLOCK"
    UNKNOWN = "UNKNOWN"

@dataclass
class ActuatorError:
    type: ErrorType
    message: str
    phase: ActuatorType
    recoverable: bool
    
    def to_dict(self):
        return {
            "type": self.type.value,
            "message": self.message,
            "phase": self.phase.value,
            "recoverable": self.recoverable
        }

@dataclass
class ActuatorRequest:
    execution_id: str
    step_id: str
    actuator_type: ActuatorType
    method: str              # GET, POST, NAVIGATE, CLICK
    url: Optional[str]
    payload: Optional[Dict]
    headers: Optional[Dict]
    selector: Optional[str]  # ONLY for Playwright
    timeout_ms: int
    metadata: Dict

@dataclass
class ActuatorResponse:
    execution_id: str
    step_id: str
    actuator_type: ActuatorType
    status: Optional[int]
    success: bool
    raw_body: Union[str, bytes]
    final_url: Optional[str]
    headers: Dict
    timing_ms: int
    artifacts: Dict
    error: Optional[ActuatorError]
