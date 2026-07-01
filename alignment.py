from dataclasses import dataclass, field
from typing import List

@dataclass
class EntityMarkers:
    trust: bool = False
    estate: bool = False
    deceased: bool = False
    llc: bool = False
    corporation: bool = False

@dataclass
class AlignmentFeatures:
    exact_match: bool = False
    token_overlap: float = 0.0
    surname_overlap: bool = False
    first_name_overlap: bool = False
    trust_indicator_diff: bool = False
    estate_indicator_diff: bool = False
    deceased_indicator_diff: bool = False
    entity_indicator_diff: bool = False

@dataclass
class AlignmentResult:
    state: str
    confidence: float
    candidates: List[str]
    explanation: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "state": self.state,
            "confidence": self.confidence,
            "candidates": self.candidates,
            "explanation": self.explanation
        }
