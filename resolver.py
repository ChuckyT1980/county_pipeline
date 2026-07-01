from dataclasses import dataclass
from typing import Optional, Dict, Any, List

@dataclass
class FieldCandidate:
    value: Any
    source: str          # "feeparcel_api", "asmt_api", "html_fallback"
    confidence: float    # 0.0 - 1.0
    raw: Dict[str, Any]

@dataclass
class ResolvedField:
    value: Any
    confidence: float
    provenance: List[str]

class FieldResolver:
    def __init__(self):
        # source reliability hierarchy
        self.source_weights = {
            "asmt_api": 0.95,
            "feeparcel_api": 0.85,
            "html_fallback": 0.60,
            "inferred": 0.40
        }

    def resolve(self, field_name: str, candidates: List[FieldCandidate]) -> ResolvedField:
        # Filter out empty candidates
        candidates = [c for c in candidates if c.value]
        
        if not candidates:
            return ResolvedField(
                value=None,
                confidence=0.0,
                provenance=[]
            )

        scored = []
        for c in candidates:
            base_weight = self.source_weights.get(c.source, 0.5)
            # adjust confidence by signal quality
            adjusted = base_weight * (c.confidence or 0.5)
            scored.append((adjusted, c))

        # sort highest confidence first
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]

        return ResolvedField(
            value=best.value,
            confidence=round(best_score, 3),
            provenance=[c.source for _, c in scored if isinstance(_, float)]
        )

class MergeEngine:
    def __init__(self, resolver: FieldResolver):
        self.resolver = resolver

    def merge(self, identity_tuple: tuple, snapshot_tuple: tuple) -> dict:
        identity, id_source = identity_tuple
        snapshot, snap_source = snapshot_tuple
        
        def candidates(field):
            out = []
            if identity.get(field):
                out.append(FieldCandidate(
                    value=identity[field],
                    source=id_source,
                    confidence=0.9,
                    raw=identity
                ))
            if snapshot.get(field):
                out.append(FieldCandidate(
                    value=snapshot[field],
                    source=snap_source,
                    confidence=0.8,
                    raw=snapshot
                ))
            return out

        resolved = {}
        for field in [
            "apn",
            "situs_address",
            "owner",
            "assessed_value",
            "land_value",
            "improvement_value",
            "tax_due",
            "mailing_address",
            "roll_category"
        ]:
            result = self.resolver.resolve(field, candidates(field))
            resolved[field] = {
                "value": result.value,
                "confidence": result.confidence,
                "provenance": result.provenance
            }

        return resolved
