from completeness import CompletenessScorer

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
