from enum import Enum
from dataclasses import dataclass
from typing import List, Tuple, Optional
from vpr2 import VPR2Decision

class StepType(str, Enum):
    HTTP_REQUEST = "HTTP_REQUEST"
    BROWSER_NAVIGATE = "BROWSER_NAVIGATE"
    BROWSER_WAIT = "BROWSER_WAIT"
    EXTRACT_DOM = "EXTRACT_DOM"
    EXTRACT_JSON = "EXTRACT_JSON"
    EXTRACT_HEADERS = "EXTRACT_HEADERS"
    COOKIE_INIT = "COOKIE_INIT"
    SESSION_BOOTSTRAP = "SESSION_BOOTSTRAP"
    FOLLOW_LINK = "FOLLOW_LINK"
    VALIDATE_APN = "VALIDATE_APN"
    STORE_ARTIFACT = "STORE_ARTIFACT"

@dataclass
class ExecutionStep:
    id: str
    type: StepType
    target: Optional[str]
    params: dict
    timeout_ms: int
    retry_policy: str  # STRICT | NONE
    outputs: List[str]

@dataclass
class ExecutionGraph:
    county: str
    vendor_class: str
    strategy: str
    steps: List[ExecutionStep]
    edges: List[Tuple[str, str]]
    expected_outputs: List[str]
    
    def to_dict(self):
        return {
            "county": self.county,
            "vendor_class": self.vendor_class,
            "strategy": self.strategy,
            "steps": [{"id": s.id, "type": s.type.value, "target": s.target} for s in self.steps],
            "edges": self.edges,
            "expected_outputs": self.expected_outputs
        }

class VPR3Compiler:
    """
    Compiles a VPR2Decision into a strict Execution Graph (IR).
    """
    def compile(self, decision: VPR2Decision) -> ExecutionGraph:
        strat = decision.acquisition_strategy.value
        
        if strat == "HTTP_ONLY":
            return self._compile_http_only(decision)
        elif strat == "COOKIE_BOOTSTRAP":
            return self._compile_cookie_bootstrap(decision)
        elif strat == "STATEFUL_BROWSER":
            return self._compile_stateful_browser(decision)
        elif strat == "HYBRID_RENDER_PIPE":
            return self._compile_hybrid_pipe(decision)
        elif strat == "NO_AUTOMATION_FEASIBLE":
            return ExecutionGraph(
                county=decision.county,
                vendor_class=decision.vendor_class.value,
                strategy=strat,
                steps=[],
                edges=[],
                expected_outputs=[]
            )
            
        raise ValueError(f"Unknown acquisition strategy: {strat}")

    def _compile_http_only(self, decision: VPR2Decision) -> ExecutionGraph:
        steps = [
            ExecutionStep("S1", StepType.HTTP_REQUEST, "tax_source", {}, 5000, "STRICT", ["raw_html"]),
            ExecutionStep("S2", StepType.EXTRACT_DOM, None, {}, 2000, "NONE", ["extracted_records"]),
            ExecutionStep("S3", StepType.VALIDATE_APN, None, {}, 1000, "NONE", ["validated_records"]),
            ExecutionStep("S4", StepType.STORE_ARTIFACT, None, {}, 1000, "NONE", ["storage_id"])
        ]
        edges = [("S1", "S2"), ("S2", "S3"), ("S3", "S4")]
        return ExecutionGraph(decision.county, decision.vendor_class.value, decision.acquisition_strategy.value, steps, edges, ["storage_id"])

    def _compile_cookie_bootstrap(self, decision: VPR2Decision) -> ExecutionGraph:
        steps = [
            ExecutionStep("S1", StepType.COOKIE_INIT, None, {}, 1000, "NONE", ["cookie_jar_init"]),
            ExecutionStep("S2", StepType.HTTP_REQUEST, "landing_page", {}, 5000, "STRICT", ["landing_resp"]),
            ExecutionStep("S3", StepType.EXTRACT_HEADERS, None, {"target": "set-cookie"}, 1000, "NONE", ["session_cookies"]),
            ExecutionStep("S4", StepType.HTTP_REQUEST, "tax_source", {"use_cookies": "session_cookies"}, 5000, "STRICT", ["raw_html"]),
            ExecutionStep("S5", StepType.VALIDATE_APN, None, {}, 1000, "NONE", ["validated_records"]),
            ExecutionStep("S6", StepType.STORE_ARTIFACT, None, {}, 1000, "NONE", ["storage_id"])
        ]
        edges = [("S1", "S2"), ("S2", "S3"), ("S3", "S4"), ("S4", "S5"), ("S5", "S6")]
        return ExecutionGraph(decision.county, decision.vendor_class.value, decision.acquisition_strategy.value, steps, edges, ["storage_id"])

    def _compile_stateful_browser(self, decision: VPR2Decision) -> ExecutionGraph:
        steps = [
            ExecutionStep("S1", StepType.BROWSER_NAVIGATE, "landing_page", {}, 15000, "STRICT", ["dom_loaded"]),
            ExecutionStep("S2", StepType.BROWSER_WAIT, None, {"condition": "network_idle"}, 5000, "NONE", ["state_ready"]),
            ExecutionStep("S3", StepType.EXTRACT_DOM, None, {"target": "hidden_inputs"}, 2000, "NONE", ["viewstate"]),
            ExecutionStep("S4", StepType.SESSION_BOOTSTRAP, None, {"inputs": "viewstate"}, 2000, "NONE", ["session_ready"]),
            ExecutionStep("S5", StepType.HTTP_REQUEST, "form_submit", {"use_session": "session_ready"}, 10000, "STRICT", ["raw_html"]),
            ExecutionStep("S6", StepType.VALIDATE_APN, None, {}, 1000, "NONE", ["validated_records"]),
            ExecutionStep("S7", StepType.STORE_ARTIFACT, None, {}, 1000, "NONE", ["storage_id"])
        ]
        edges = [("S1", "S2"), ("S2", "S3"), ("S3", "S4"), ("S4", "S5"), ("S5", "S6"), ("S6", "S7")]
        return ExecutionGraph(decision.county, decision.vendor_class.value, decision.acquisition_strategy.value, steps, edges, ["storage_id"])

    def _compile_hybrid_pipe(self, decision: VPR2Decision) -> ExecutionGraph:
        steps = [
            ExecutionStep("S1", StepType.BROWSER_NAVIGATE, "landing_page", {}, 15000, "STRICT", ["dom_loaded"]),
            ExecutionStep("S2", StepType.EXTRACT_DOM, None, {"target": "api_links"}, 2000, "NONE", ["api_endpoints"]),
            ExecutionStep("S3", StepType.FOLLOW_LINK, "api_endpoints", {}, 2000, "NONE", ["api_route"]),
            ExecutionStep("S4", StepType.HTTP_REQUEST, "api_route", {"mode": "bulk"}, 15000, "STRICT", ["raw_json"]),
            ExecutionStep("S5", StepType.VALIDATE_APN, None, {}, 1000, "NONE", ["validated_records"]),
            ExecutionStep("S6", StepType.STORE_ARTIFACT, None, {}, 1000, "NONE", ["storage_id"])
        ]
        edges = [("S1", "S2"), ("S2", "S3"), ("S3", "S4"), ("S4", "S5"), ("S5", "S6")]
        return ExecutionGraph(decision.county, decision.vendor_class.value, decision.acquisition_strategy.value, steps, edges, ["storage_id"])
