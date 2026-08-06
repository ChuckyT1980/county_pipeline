from enum import Enum
from dataclasses import dataclass
from typing import List, Literal, Optional, Dict, Any

class DriftType(str, Enum):
    NO_DRIFT = "NO_DRIFT"
    MICRO_DRIFT = "MICRO_DRIFT"
    MACRO_DRIFT = "MACRO_DRIFT"
    FULL_SCHEMA_REPLACEMENT = "FULL_SCHEMA_REPLACEMENT"

class SuggestedAction(str, Enum):
    NONE = "NONE"
    RE_FINGERPRINT_SDA1 = "RE-FINGERPRINT_SDA1"
    UPDATE_SCDA_MAPPING = "UPDATE_SCDA_MAPPING"
    TRIGGER_VPR_REPLAN = "TRIGGER_VPR_REPLAN"
    REBUILD_VPR_DOMAIN_MODEL = "REBUILD_VPR_DOMAIN_MODEL"

@dataclass
class CVA1AnomalyEvent:
    county_id: str
    vendor_class: str
    schema_id: str
    failure_type: str  # SOFT_SCHEMA_DRIFT | HARD_SCHEMA_BREAK
    raw_payload_snapshot: Dict[str, Any]
    dom_signature: Dict[str, Any]
    token_signature: Dict[str, Any]
    timestamp: float

@dataclass
class StructuralDriftReport:
    drift_type: DriftType
    confidence: float
    affected_entities: List[str]
    migration_required: bool
    suggested_action: SuggestedAction
    stability_delta: float
    explanation: str
