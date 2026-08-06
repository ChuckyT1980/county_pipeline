from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

class ExecutionMode(str, Enum):
    FULL = "FULL"                       # Normal execution, adaptive branching allowed
    STRICT = "STRICT"                   # No retries, minimal branching
    OBSERVATION_ONLY = "OBSERVATION_ONLY" # No execution, only telemetry collected

@dataclass
class InstrumentDivergenceFunction:
    delta_efs: float
    delta_vsi: float
    delta_fme: float
    transition_label: str
    ivd: float

@dataclass
class ActionConstraintVector:
    allowed_strategies: List[str]
    retry_budget: int
    escalation_threshold: float
    vendor_class_lock: Optional[str]
    execution_mode: ExecutionMode
    confidence_floor: float
    entropy_cap: float
    diagnostic_reason: str = ""
    # Global Invariants
    allow_recompile: bool = True
    allow_strategy_switch: bool = True
    allow_retry: bool = True
    allow_actuator_fallback: bool = True
    
    # CGR-1 Instrument Trust
    instrument_authority_weights: dict = None
