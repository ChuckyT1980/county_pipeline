from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, List
from sda2_schemas import StructuralDriftReport, CVA1AnomalyEvent

class PatchType(str, Enum):
    SELECTOR_UPDATE = "SELECTOR_UPDATE"
    FIELD_REMAP = "FIELD_REMAP"
    STRATEGY_PRUNE = "STRATEGY_PRUNE"
    FULL_SCHEMA_REWRITE = "FULL_SCHEMA_REWRITE"

@dataclass
class RecompileProposal:
    target_registry: str # "schema_registry" | "vpr_registry"
    vendor_class: str
    drift_source_event_id: str
    patch_type: PatchType
    before_state: Dict[str, Any]
    after_state: Dict[str, Any]
    confidence: float
    justification_trace: StructuralDriftReport
    risk_score: float

@dataclass
class StratifiedReplaySet:
    anchor_trace: CVA1AnomalyEvent
    stable_window: List[Any] # List[CARS2Trace] in full impl
    drift_samples: List[CVA1AnomalyEvent]
