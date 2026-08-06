from enum import Enum
from dataclasses import dataclass
from typing import List, Tuple
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from eer1_schemas import SessionContext

class ISLProbeType(str, Enum):
    # Temporal Starvation (HTTP fast vs Playwright normal)
    TEMPORAL_STARVATION = "TEMPORAL_STARVATION"
    
    # Rendering Deprivation (HTTP normal vs Playwright early cutoff)
    RENDERING_DEPRIVATION = "RENDERING_DEPRIVATION"
    
    # Desynchronization (HTTP 10ms vs Playwright networkidle)
    DESYNCHRONIZATION = "DESYNCHRONIZATION"
    
    # BASELINE (For control mapping)
    BASELINE = "BASELINE"

@dataclass
class ISL1ProbePair:
    type: ISLProbeType
    http_graph: ExecutionGraph
    browser_graph: ExecutionGraph
    session: SessionContext

class ISLProbeGenerator:
    """
    Generates controlled observation window constraints to force Phase Transition Boundaries.
    """
    
    @staticmethod
    def generate_matrix(county: str, vendor_class: str, target_url: str) -> List[ISL1ProbePair]:
        pairs = []
        
        # 1. BASELINE
        h_base = ExecutionStep(f"{county}_h_base", StepType.HTTP_REQUEST, target_url, {}, 5000, "NONE", ["raw_html"])
        b_base = ExecutionStep(f"{county}_b_base", StepType.BROWSER_NAVIGATE, target_url, {"metadata": {"wait_until": "domcontentloaded"}}, 10000, "NONE", ["raw_html"])
        pairs.append(ISL1ProbePair(
            ISLProbeType.BASELINE,
            ExecutionGraph(county, vendor_class, "HTTP_ONLY", [h_base], [], ["raw_html"]),
            ExecutionGraph(county, vendor_class, "BROWSER_ONLY", [b_base], [], ["raw_html"]),
            SessionContext()
        ))
        
        # 2. TEMPORAL STARVATION
        # HTTP is aggressively starved (50ms), Playwright gets full time (10000ms)
        h_starve = ExecutionStep(f"{county}_h_starve", StepType.HTTP_REQUEST, target_url, {}, 50, "NONE", ["raw_html"])
        b_starve = ExecutionStep(f"{county}_b_starve", StepType.BROWSER_NAVIGATE, target_url, {"metadata": {"wait_until": "domcontentloaded"}}, 10000, "NONE", ["raw_html"])
        pairs.append(ISL1ProbePair(
            ISLProbeType.TEMPORAL_STARVATION,
            ExecutionGraph(county, vendor_class, "HTTP_ONLY", [h_starve], [], ["raw_html"]),
            ExecutionGraph(county, vendor_class, "BROWSER_ONLY", [b_starve], [], ["raw_html"]),
            SessionContext()
        ))
        
        # 3. RENDERING DEPRIVATION
        # HTTP gets normal time, Playwright is forced to snapshot immediately ("commit" phase) or fast timeout (1000ms)
        h_deprive = ExecutionStep(f"{county}_h_deprive", StepType.HTTP_REQUEST, target_url, {}, 5000, "NONE", ["raw_html"])
        b_deprive = ExecutionStep(f"{county}_b_deprive", StepType.BROWSER_NAVIGATE, target_url, {"metadata": {"wait_until": "commit"}}, 1500, "NONE", ["raw_html"])
        pairs.append(ISL1ProbePair(
            ISLProbeType.RENDERING_DEPRIVATION,
            ExecutionGraph(county, vendor_class, "HTTP_ONLY", [h_deprive], [], ["raw_html"]),
            ExecutionGraph(county, vendor_class, "BROWSER_ONLY", [b_deprive], [], ["raw_html"]),
            SessionContext()
        ))
        
        # 4. DESYNCHRONIZATION
        # HTTP is given just enough time to get headers but maybe truncate body (250ms)
        # Playwright waits for full absolute network silence ("networkidle")
        h_desync = ExecutionStep(f"{county}_h_desync", StepType.HTTP_REQUEST, target_url, {}, 250, "NONE", ["raw_html"])
        b_desync = ExecutionStep(f"{county}_b_desync", StepType.BROWSER_NAVIGATE, target_url, {"metadata": {"wait_until": "networkidle"}}, 15000, "NONE", ["raw_html"])
        pairs.append(ISL1ProbePair(
            ISLProbeType.DESYNCHRONIZATION,
            ExecutionGraph(county, vendor_class, "HTTP_ONLY", [h_desync], [], ["raw_html"]),
            ExecutionGraph(county, vendor_class, "BROWSER_ONLY", [b_desync], [], ["raw_html"]),
            SessionContext()
        ))
        
        return pairs
