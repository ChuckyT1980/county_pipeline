from enum import Enum
from dataclasses import dataclass
from typing import Literal, Optional, Any

class ViolationType(str, Enum):
    NONE = "NONE"
    SOFT_SCHEMA_DRIFT = "SOFT_SCHEMA_DRIFT"             # Legacy generic soft
    HARD_SCHEMA_BREAK = "HARD_SCHEMA_BREAK"             # Legacy generic hard
    EXECUTION_UNBOUND = "EXECUTION_UNBOUND"             
    UNDECLARED_RETRY_BEHAVIOR = "UNDECLARED_RETRY_BEHAVIOR" 
    TELEMETRY_INCOHERENCE = "TELEMETRY_INCOHERENCE"       
    
    # ERE-1 Intermediate Observability States
    SOFT_BLOCK_CAPTCHA = "SOFT_BLOCK_CAPTCHA"
    PARTIAL_DOM_RENDER = "PARTIAL_DOM_RENDER"
    REDIRECT_CHAIN_OBSERVED = "REDIRECT_CHAIN_OBSERVED"
    SESSION_CHALLENGE = "SESSION_CHALLENGE"

class AffectedLayer(str, Enum):
    VPR = "VPR"           # Planning error
    EER = "EER"           # Execution error
    CARS = "CARS"         # Constraint contradiction
    DISPATCH = "DISPATCH" # Environmental reality (Schema drifts)

@dataclass
class ConstraintViolationReport:
    violation_type: ViolationType
    severity: float             # 0.0 to 1.0
    affected_layer: Optional[AffectedLayer]
    hard_halt: bool             # Should pipeline stop completely
    quarantine_execution: bool  # Should CARS-2 route to anomaly buffer instead of EMA
    explanation: str
    raw_evidence: Any = None
