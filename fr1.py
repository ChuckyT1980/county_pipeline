import re
from dataclasses import dataclass, field
from typing import List, Dict, Any
from itertools import combinations


@dataclass
class ReconciledField:
    value: str
    confidence: float
    state: str  # VERIFIED | HIGH_CONFIDENCE | PARTIAL_CONFLICT | CONFLICTED | UNKNOWN
    sources: List[str]
    normalized_values: List[str]

    def __post_init__(self):
        if self.value is None:
            self.value = ""

    def to_dict(self):
        return {
            "value": self.value,
            "confidence": self.confidence,
            "state": self.state,
            "sources": self.sources,
            "normalized_values": self.normalized_values
        }

def normalize(value: str) -> str:
    if value is None:
        return ""

    value = str(value).lower().strip()
    value = re.sub(r"[^\w\s]", "", value)
    value = re.sub(r"\s+", " ", value)

    # minimal expansions
    value = value.replace("tr", "trust")
    value = value.replace("decd", "deceased")

    return value

def similarity(a: str, b: str) -> float:
    a_tokens = set(a.split())
    b_tokens = set(b.split())

    if not a_tokens or not b_tokens:
        return 0.0

    overlap = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)

    jaccard = overlap / union

    # boost exact match
    if a == b:
        return 1.0

    return jaccard

def reconcile_field(field_values: Dict[str, str]) -> ReconciledField:
    """
    field_values = {
        "assessor": "...",
        "tax": "...",
        "parcel": "..."
    }
    """

    if not field_values:
        return ReconciledField(
            value="",
            confidence=0.0,
            state="UNKNOWN",
            sources=[],
            normalized_values=[]
        )

    # Clean out empty sources
    field_values = {k: v for k, v in field_values.items() if v}
    if not field_values:
        return ReconciledField(
            value="",
            confidence=0.0,
            state="UNKNOWN",
            sources=[],
            normalized_values=[]
        )

    sources = list(field_values.keys())
    values = list(field_values.values())
    normalized = [normalize(v) for v in values]

    if len(values) == 1:
        # Single source defaults to HIGH_CONFIDENCE because it's unverified by cross-referencing
        return ReconciledField(
            value=values[0],
            confidence=0.80,
            state="HIGH_CONFIDENCE",
            sources=sources,
            normalized_values=normalized
        )

    # compute pairwise similarity
    scores = []
    for (i, j) in combinations(range(len(values)), 2):
        scores.append(similarity(normalized[i], normalized[j]))

    avg_similarity = sum(scores) / len(scores) if scores else 1.0

    # pick "best representative value"
    value = max(values, key=lambda v: len(v or ""))

    # classification
    if avg_similarity >= 0.85:
        state = "VERIFIED"
        confidence = 0.95
    elif avg_similarity >= 0.60:
        state = "HIGH_CONFIDENCE"
        confidence = 0.80
    elif avg_similarity >= 0.30:
        state = "PARTIAL_CONFLICT"
        confidence = 0.55
    else:
        state = "CONFLICTED"
        confidence = 0.25

    return ReconciledField(
        value=value,
        confidence=confidence,
        state=state,
        sources=sources,
        normalized_values=normalized
    )
