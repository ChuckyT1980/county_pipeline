from enum import Enum
from dataclasses import dataclass, field
from typing import Literal, Optional, List, Dict, Any
from ddl1_schemas import DeterministicExecutionTrace

class RuntimeFailureType(str, Enum):
    STEP_TIMEOUT = "STEP_TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    HTTP_ERROR = "HTTP_ERROR"
    BROWSER_CRASH = "BROWSER_CRASH"
    INVALID_STEP_OUTPUT = "INVALID_STEP_OUTPUT"
    MISSING_EXPECTED_OUTPUT = "MISSING_EXPECTED_OUTPUT"
    DISPATCH_MISMATCH = "DISPATCH_MISMATCH"
    SESSION_LOST = "SESSION_LOST"
    UNKNOWN_RUNTIME_FAILURE = "UNKNOWN_RUNTIME_FAILURE"

@dataclass
class ExecutionResult:
    step_id: str
    status: Literal["SUCCESS", "FAILURE"]
    response: Optional[Dict[str, Any]]
    latency_ms: int
    error_type: Optional[str]
    output_hash: Optional[str]
    trace: Optional[DeterministicExecutionTrace] = None

@dataclass
class StepFailure:
    step_id: str
    failure_type: RuntimeFailureType
    message: str
    timestamp: str
    partial_output: Optional[Dict[str, Any]]

@dataclass
class ExecutionFailureState:
    failed: bool
    failed_step_id: Optional[str]
    failure_type: Optional[RuntimeFailureType]
    halt_reason: str
    partial_execution_trace: List[ExecutionResult]

@dataclass
class SessionContext:
    cookies: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    browser_state: Optional[Any] = None

@dataclass
class RuntimeTelemetry:
    execution_graph_id: str
    step_results: List[ExecutionResult]
    strategy_planned: str
    strategy_observed: str
    failure_step: Optional[str]
    total_latency_ms: int
    apn_validations: dict
    failure_context: Optional[Dict[str, Any]] = None
    
    def to_dict(self):
        return {
            "execution_graph_id": self.execution_graph_id,
            "strategy_planned": self.strategy_planned,
            "strategy_observed": self.strategy_observed,
            "failure_step": self.failure_step,
            "total_latency_ms": self.total_latency_ms,
            "failure_context": self.failure_context,
            "step_results": [
                {
                    "step_id": r.step_id, 
                    "status": r.status, 
                    "latency_ms": r.latency_ms,
                    "error_type": r.error_type
                } for r in self.step_results
            ]
        }
