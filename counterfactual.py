import copy
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class CounterfactualUpgrade:
    field: str
    action: str
    expected_delta: float
    cost: str
    confidence_gain: float

@dataclass
class CounterfactualResult:
    current_score: float
    max_theoretical_score: float
    best_upgrades: List[CounterfactualUpgrade]
    bottleneck: str

class CounterfactualEngine:
    def __init__(self, scorer):
        self.scorer = scorer

    def _generate_actions(self, merged_record: dict) -> List[Dict]:
        actions = []

        # Missing field resolution opportunities
        for field, node in merged_record.items():
            conf = node.get("confidence", 0.0)
            if conf < 0.5:
                actions.append({
                    "field": field,
                    "action": "increase_confidence",
                    "delta_type": "sensor_upgrade",
                    "cost": "medium"
                })

        # Missing contact data handling
        if not merged_record.get("mailing_address", {}).get("value"):
            actions.append({
                "field": "mailing_address",
                "action": "resolve_missing_field",
                "delta_type": "data_enrichment",
                "cost": "low"
            })
            
        # Value missing (equity proxy)
        if not merged_record.get("assessed_value", {}).get("value"):
            actions.append({
                "field": "assessed_value",
                "action": "resolve_missing_field",
                "delta_type": "data_enrichment",
                "cost": "medium"
            })

        return actions

    def _simulate(self, merged_record: dict, distress_event: dict, action: Dict) -> float:
        simulated = copy.deepcopy(merged_record)
        field = action["field"]

        if action["action"] == "resolve_missing_field":
            simulated[field] = simulated.get(field, {})
            # Mock value that triggers positive scoring
            if field == "mailing_address":
                simulated[field]["value"] = "VERIFIED_ADDRESS"
            elif field == "assessed_value":
                simulated[field]["value"] = 500000.0
            else:
                simulated[field]["value"] = "RESOLVED"
            simulated[field]["confidence"] = 0.9

        elif action["action"] == "increase_confidence":
            simulated[field] = simulated.get(field, {})
            simulated[field]["confidence"] = min(1.0, simulated[field].get("confidence", 0) + 0.35)

        # Re-score through existing system
        score_data = self.scorer.score(simulated, distress_event)
        return score_data["final_score"]

    def _estimate_confidence_gain(self, action: Dict) -> float:
        mapping = {
            "resolve_missing_field": 0.30,
            "increase_confidence": 0.25,
            "replace_weak_sensor_with_api": 0.55
        }
        return mapping.get(action["action"], 0.1)
        
    def _identify_bottleneck(self, merged_record: dict) -> str:
        if not merged_record.get("mailing_address", {}).get("value"):
            return "missing_identity_resolution"
            
        if any(node.get("confidence", 0) < 0.4 for node in merged_record.values()):
            return "low_field_confidence_cluster"

        return "score_saturation_limited_by_core_features"

    def analyze(self, merged_record: dict, distress_event: dict, current_score: float) -> CounterfactualResult:
        actions = self._generate_actions(merged_record)

        best_upgrades = []
        best_score = current_score

        for action in actions:
            new_score = self._simulate(merged_record, distress_event, action)
            delta = new_score - current_score
            
            if delta > 0:
                confidence_gain = self._estimate_confidence_gain(action)
                best_upgrades.append(
                    CounterfactualUpgrade(
                        field=action["field"],
                        action=action["action"],
                        expected_delta=round(delta, 2),
                        cost=action["cost"],
                        confidence_gain=confidence_gain
                    )
                )
                best_score = max(best_score, new_score)

        best_upgrades.sort(key=lambda x: x.expected_delta, reverse=True)
        bottleneck = self._identify_bottleneck(merged_record)

        return CounterfactualResult(
            current_score=current_score,
            max_theoretical_score=round(best_score, 2),
            best_upgrades=best_upgrades[:3],
            bottleneck=bottleneck
        )
