from completeness import CompletenessScorer
from canonical import IntelligenceRecord

class UncertaintyAwareScorer:
    def __init__(self, completeness_scorer: CompletenessScorer):
        self.completeness_scorer = completeness_scorer

    def compute_uncertainty_multiplier(self, completeness) -> float:
        # weighted blend of trust signals
        base_trust = (
            completeness.confidence_score * 0.7 +
            completeness.coverage_score * 0.3
        )
        
        # nonlinear dampening curve
        multiplier = base_trust ** 1.6
        return max(0.25, min(multiplier, 1.0))

    def compute_base_opportunity_score(self, merged_record, event) -> (float, dict):
        score = 0
        signals = {}

        # 1. DISTRESS PERSISTENCE
        persistence = 2025 - int(event.get("default_year", 2025))
        score += persistence * 12
        signals["persistence"] = persistence

        # 2. FINANCIAL PRESSURE
        amount_due = float(event.get("amount_due", 0))
        score += min(amount_due / 500, 60)
        signals["amount_due"] = amount_due

        # 3. EQUITY PROXY
        assessed_value = merged_record.get("assessed_value", {}).get("value")
        if assessed_value and float(assessed_value) > 0:
            assessed_value = float(assessed_value)
            distress_ratio = amount_due / assessed_value
            score += min(distress_ratio * 100, 40)
            signals["equity_proxy"] = distress_ratio
            if assessed_value < 200000:
                score += 15
        else:
            score += 8
            signals["equity_proxy"] = None

        # 4. ABSENTEE SIGNAL
        situs_address = merged_record.get("situs_address", {}).get("value")
        mailing = merged_record.get("mailing_address", {}).get("value")
        signals["absentee"] = False
        
        if mailing and situs_address:
            if str(mailing).strip().lower() != str(situs_address).strip().lower():
                score += 20
                signals["absentee"] = True
        if not situs_address:
            score += 10
            signals["absentee"] = True # Implicitly absentee if no situs

        # 5. LAND / SIMPLICITY BONUS
        # We don't have land_use in our current resolve block, but we can look at situs
        signals["land_flag"] = False
        if not situs_address: # simple proxy for land right now
            score += 12
            signals["land_flag"] = True

        return round(score, 2), signals

    def score(self, merged_record: dict, distress_event: dict):
        # 1. COMPLETENESS
        completeness = self.completeness_scorer.score(merged_record)

        # 2. BASE SCORE
        base_score, signals = self.compute_base_opportunity_score(merged_record, distress_event)

        # 3. UNCERTAINTY MULTIPLIER
        uncertainty_multiplier = self.compute_uncertainty_multiplier(completeness)

        # 4. FINAL SCORE
        final_score = base_score * uncertainty_multiplier

        # Rank Bucket
        if final_score >= 80:
            bucket = "A+ (Acquisition Priority)"
        elif final_score >= 50:
            bucket = "A (Strong Lead)"
        elif final_score >= 30:
            bucket = "B (Watchlist)"
        else:
            bucket = "C (Noise)"

        return {
            "final_score": round(final_score, 2),
            "base_score": base_score,
            "uncertainty_multiplier": round(uncertainty_multiplier, 3),
            "coverage": completeness.coverage_score,
            "confidence": completeness.confidence_score,
            "missing_fields": completeness.missing_fields,
            "weak_fields": completeness.weak_fields,
            "signals": signals,
            "rank_bucket": bucket
        }


def generate_states(record: IntelligenceRecord) -> None:
    """Populate Layer 3 States from Layer 1 Facts and Layer 2 Signals."""
    facts = record.facts
    signals = record.signals
    states = record.states

    # ownership_complexity: high for deceased/trust/entity/multi
    complexity = 0.1
    if signals.deceased_owner:
        complexity += 0.5
    if signals.trust_owner:
        complexity += 0.3
    if signals.entity_owner:
        complexity += 0.2
    if signals.multiple_owners:
        complexity += 0.15
    states.ownership_complexity = min(complexity, 1.0)

    # heir_probability: high for deceased, zero otherwise
    states.heir_probability = 0.9 if signals.deceased_owner else 0.0

    # ownership_stability: inverse of complexity
    states.ownership_stability = max(0.0, 1.0 - states.ownership_complexity)

    # tax_pressure: based on amount_due and default_date
    amount = float(facts.amount_due or 0)
    pressure = min(amount / 10000.0, 1.0) if amount > 0 else 0.0
    if facts.default_date:
        pressure += 0.1
    states.tax_pressure = min(pressure, 1.0)

    # property_utility_score: based on assessed_value, acreage, improved_vs_vacant, access_quality
    util = 0.0
    if facts.improved_vs_vacant is True:
        util += 0.4
    elif facts.improved_vs_vacant is False:
        util += 0.1

    if facts.assessed_value and facts.assessed_value > 0:
        util += min(facts.assessed_value / 500000.0, 1.0) * 0.4

    if facts.acreage and facts.acreage > 0:
        util += min(facts.acreage / 5.0, 1.0) * 0.2

    access = (facts.access_quality or "").lower()
    if access in ("excellent", "good"):
        util += 0.1
    elif access in ("poor", "very_poor"):
        util -= 0.1

    states.property_utility_score = max(0.0, min(util, 1.0))


def process_record(record: IntelligenceRecord) -> None:
    """Process an IntelligenceRecord through scoring to produce opportunity and confidence."""
    generate_states(record)

    facts = record.facts
    signals = record.signals
    states = record.states

    # Compute attractiveness score (0-100+)
    score = 0.0

    # Distress persistence (default_date)
    if facts.default_date:
        try:
            default_year = int(str(facts.default_date).split("-")[0])
            persistence = max(0, 2025 - default_year)
        except Exception:
            persistence = 0
        score += persistence * 3

    # Financial pressure
    amount = float(facts.amount_due or 0)
    score += min(amount / 100.0, 30)

    # Equity proxy
    if facts.assessed_value and facts.assessed_value > 0:
        distress_ratio = amount / facts.assessed_value
        score += min(distress_ratio * 100, 25)
        if facts.assessed_value < 200000:
            score += 10

    # Absentee owner bonus
    if signals.out_of_state_owner and not signals.owner_occupied:
        score += 15
    elif not signals.owner_occupied:
        score += 5

    # Land/vacant bonus (simpler = easier acquisition)
    if facts.improved_vs_vacant is False:
        score += 8

    # Motivation signals
    if signals.deceased_owner:
        score += 12
    if signals.trust_owner:
        score += 8

    # Utility multiplier
    score = score * (0.5 + 0.5 * states.property_utility_score)

    # Resolution difficulty
    difficulty = states.ownership_complexity * 0.6 + states.tax_pressure * 0.4
    if signals.deceased_owner:
        difficulty += 0.1
    difficulty = min(difficulty, 1.0)

    # Tier
    if score >= 70:
        tier = 1
    elif score >= 45:
        tier = 2
    elif score >= 20:
        tier = 3
    else:
        tier = 4

    # Explanation
    reasons = []
    if signals.deceased_owner:
        reasons.append("deceased owner")
    if signals.trust_owner:
        reasons.append("trust ownership")
    if signals.out_of_state_owner:
        reasons.append("absentee owner")
    if amount > 0:
        reasons.append(f"${amount:,.0f} delinquent")
    if facts.improved_vs_vacant is False:
        reasons.append("vacant land")
    explanation = "; ".join(reasons) if reasons else "low distress signals"

    record.opportunity.attractiveness_score = round(score, 2)
    record.opportunity.resolution_difficulty = round(difficulty, 2)
    record.opportunity.tier = tier
    record.opportunity.record_explanation = explanation

    # Confidence
    data_conf = 1.0
    if facts.assessed_value is None:
        data_conf -= 0.2
    if facts.acreage is None:
        data_conf -= 0.1
    if facts.improved_vs_vacant is None:
        data_conf -= 0.1
    if facts.access_quality is None:
        data_conf -= 0.1
    if facts.default_date is None:
        data_conf -= 0.05

    ownership_conf = 1.0
    if facts.owner.state not in ("VERIFIED", "HIGH_CONFIDENCE"):
        ownership_conf -= 0.3
    if not facts.owner.value or len(str(facts.owner.value)) < 5:
        ownership_conf -= 0.4
    if facts.mailing_address.state == "UNKNOWN" or not facts.mailing_address.value:
        ownership_conf -= 0.2

    valuation_conf = 1.0
    if facts.assessed_value is None or facts.assessed_value <= 0:
        valuation_conf -= 0.5
    if facts.improvement_value is None:
        valuation_conf -= 0.1

    record.confidence.data_confidence = max(0.0, round(data_conf, 2))
    record.confidence.ownership_confidence = max(0.0, round(ownership_conf, 2))
    record.confidence.valuation_confidence = max(0.0, round(valuation_conf, 2))
    record.confidence.overall_confidence = round(
        (record.confidence.data_confidence +
         record.confidence.ownership_confidence +
         record.confidence.valuation_confidence) / 3.0, 2
    )
