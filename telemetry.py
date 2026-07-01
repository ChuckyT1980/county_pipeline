from dataclasses import dataclass
from typing import List, Dict, Optional

COMPLIANCE_FLAGS = {
    "UNEXPECTED_BROWSER_USAGE",
    "MISSING_COOKIE_BOOTSTRAP",
    "UNDECLARED_SESSION_STATE",
    "UNTRACKED_REDIRECT",
    "DOM_VS_HTTP_MISMATCH"
}

@dataclass
class ExecutionTelemetry:
    county: str
    strategy_planned: str
    strategy_executed: str
    step_trace: List[Dict]
    failure_step: Optional[str]
    failure_reason: Optional[str]
    execution_path_hash: str
    apns_extracted: int
    apns_validated: int
    compliance_flags: List[str]
    
    def calculate_strategy_accuracy(self) -> float:
        """
        Strategy Accuracy = (planned == executed) AND (no compliance violations) AND (expected outputs met)
        We use a simple 1.0 or 0.0 here for the top-level binary correctness.
        """
        if self.strategy_planned != self.strategy_executed:
            return 0.0
        if len(self.compliance_flags) > 0:
            return 0.0
        if self.failure_step is not None:
            # If the graph failed to complete its execution, accuracy is technically 0 
            # (it didn't achieve its end state), though we could be more granular.
            return 0.0
            
        return 1.0
        
    def to_dict(self):
        return {
            "county": self.county,
            "strategy_planned": self.strategy_planned,
            "strategy_executed": self.strategy_executed,
            "strategy_accuracy_score": self.calculate_strategy_accuracy(),
            "failure_step": self.failure_step,
            "failure_reason": self.failure_reason,
            "execution_path_hash": self.execution_path_hash,
            "apns_extracted": self.apns_extracted,
            "apns_validated": self.apns_validated,
            "compliance_flags": self.compliance_flags,
            "step_trace": self.step_trace
        }
