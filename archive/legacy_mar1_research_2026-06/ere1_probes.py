from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Any
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from eer1_schemas import SessionContext

class ProbeType(str, Enum):
    BASELINE = "BASELINE"
    MISSING_REFERER = "MISSING_REFERER"
    STALE_SESSION = "STALE_SESSION"
    MOBILE_USER_AGENT = "MOBILE_USER_AGENT"
    FAST_TIMEOUT = "FAST_TIMEOUT"

@dataclass
class ERE1Probe:
    type: ProbeType
    graph: ExecutionGraph
    session: SessionContext

class ProbeGenerator:
    """
    Generates controlled HTTP perturbations to expand the observability manifold.
    Instrument invariance is strictly preserved (pure HTTP, no execution layer shifts).
    """
    
    @staticmethod
    def generate_matrix(county: str, vendor_class: str, target_url: str) -> List[ERE1Probe]:
        probes = []
        
        # 1. BASELINE (Neutral GET, Standard Timeout, Empty Session)
        step_base = ExecutionStep(f"{county}_base", StepType.HTTP_REQUEST, target_url, {}, 5000, "NONE", ["raw_html"])
        probes.append(ERE1Probe(ProbeType.BASELINE, ExecutionGraph(county, vendor_class, "HTTP_ONLY", [step_base], [], ["raw_html"]), SessionContext()))
        
        # 2. MISSING REFERER (WAF Sensitivity Test)
        # We simulate a "missing referer" or "direct navigation" by explicitly setting headers in the params
        # Wait, the physical actuator uses session.cookies or explicitly passed headers. We can just set headers.
        step_ref = ExecutionStep(f"{county}_ref", StepType.HTTP_REQUEST, target_url, {"headers": {"Referer": ""}}, 5000, "NONE", ["raw_html"])
        probes.append(ERE1Probe(ProbeType.MISSING_REFERER, ExecutionGraph(county, vendor_class, "HTTP_ONLY", [step_ref], [], ["raw_html"]), SessionContext()))
        
        # 3. STALE SESSION (Session Dependency Test)
        step_stale = ExecutionStep(f"{county}_stale", StepType.HTTP_REQUEST, target_url, {}, 5000, "NONE", ["raw_html"])
        sess_stale = SessionContext()
        sess_stale.cookies["ASP.NET_SessionId"] = "INVALID_STALE_MOCK_123"
        probes.append(ERE1Probe(ProbeType.STALE_SESSION, ExecutionGraph(county, vendor_class, "HTTP_ONLY", [step_stale], [], ["raw_html"]), sess_stale))
        
        # 4. MOBILE USER AGENT (Structural Routing Test)
        step_ua = ExecutionStep(f"{county}_ua", StepType.HTTP_REQUEST, target_url, {"headers": {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"}}, 5000, "NONE", ["raw_html"])
        probes.append(ERE1Probe(ProbeType.MOBILE_USER_AGENT, ExecutionGraph(county, vendor_class, "HTTP_ONLY", [step_ua], [], ["raw_html"]), SessionContext()))
        
        # 5. FAST TIMEOUT (Latency Envelope Test)
        # Hard cap at 500ms to observe latency bounds vs hard rejections
        step_fast = ExecutionStep(f"{county}_fast", StepType.HTTP_REQUEST, target_url, {}, 500, "NONE", ["raw_html"])
        probes.append(ERE1Probe(ProbeType.FAST_TIMEOUT, ExecutionGraph(county, vendor_class, "HTTP_ONLY", [step_fast], [], ["raw_html"]), SessionContext()))
        
        return probes
