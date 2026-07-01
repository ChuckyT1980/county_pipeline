from dataclasses import dataclass
from typing import Dict, List

@dataclass
class CompletenessReport:
    coverage_score: float          # 0-1 (how complete the record is)
    confidence_score: float        # 0-1 (how reliable the data is overall)
    weighted_quality_score: float  # combined metric used downstream
    missing_fields: List[str]
    weak_fields: List[str]

class CompletenessScorer:
    def __init__(self):
        # importance weights per field
        self.field_weights = {
            "apn": 1.0,
            "owner": 0.9,
            "situs_address": 0.9,
            "assessed_value": 0.8,
            "assessed_land": 0.6,
            "assessed_improvement": 0.6,
            "mailing_address": 0.7,
            "roll_category": 0.5
        }

    def score(self, resolved_record: Dict[str, dict]) -> CompletenessReport:
        total_weight = 0.0
        coverage_weight = 0.0
        confidence_sum = 0.0
        confidence_weight = 0.0
        missing = []
        weak = []

        for field, weight in self.field_weights.items():
            node = resolved_record.get(field)

            # MISSING FIELD
            if not node or node.get("value") is None:
                missing.append(field)
                continue

            total_weight += weight
            coverage_weight += weight
            conf = node.get("confidence", 0.0)
            
            confidence_sum += conf * weight
            confidence_weight += weight

            # weak signal detection
            if conf < 0.65:
                weak.append(field)

        # COVERAGE SCORE
        coverage_score = coverage_weight / sum(self.field_weights.values())

        # CONFIDENCE SCORE
        confidence_score = (
            confidence_sum / confidence_weight
            if confidence_weight > 0 else 0.0
        )

        # COMBINED QUALITY SCORE
        weighted_quality_score = coverage_score * 0.6 + confidence_score * 0.4

        return CompletenessReport(
            coverage_score=round(coverage_score, 3),
            confidence_score=round(confidence_score, 3),
            weighted_quality_score=round(weighted_quality_score, 3),
            missing_fields=missing,
            weak_fields=weak
        )
