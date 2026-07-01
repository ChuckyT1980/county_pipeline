class DecisionTraceCompiler:
    def compile_trace(self, lead: dict) -> dict:
        score_data = lead.get("score_data", {})
        signals = score_data.get("signals", {})
        missing_fields = score_data.get("missing_fields", [])
        weak_fields = score_data.get("weak_fields", [])
        
        score = score_data.get("final_score", 0)
        coverage = score_data.get("coverage", 0)
        confidence = score_data.get("confidence", 0)

        # 1. Action Mapping
        if score >= 80 and coverage > 0.8:
            action = "CALL FIRST"
        elif score >= 80:
            action = "CALL FIRST (REQUIRES ENRICHMENT)"
        elif score >= 50:
            action = "HIGH PRIORITY REVIEW"
        elif coverage < 0.5:
            action = "REQUIRES ENRICHMENT"
        else:
            action = "WATCHLIST"

        # 2. Driver Extraction
        drivers = []
        if signals.get("persistence", 0) >= 3:
            drivers.append(f"{signals['persistence']}-year tax delinquency")
        if signals.get("amount_due", 0) > 3000:
            drivers.append(f"High tax burden (${signals['amount_due']})")
        if signals.get("absentee"):
            drivers.append("Absentee owner signal")

        # 3. Blocker Extraction (Data Quality Drag)
        blockers = []
        for field in missing_fields:
            blockers.append(f"Missing {field} (Coverage Drag)")
        for field in weak_fields:
            blockers.append(f"Weak signal on {field} (Confidence Drag)")

        # 4. Confidence Summary Template
        conf_summary = ""
        if confidence > 0.8:
            conf_summary = "High signal strength"
        elif confidence > 0.5:
            conf_summary = "Moderate signal strength"
        else:
            conf_summary = "Weak signal strength"
            
        if missing_fields:
            conf_summary += f", but incomplete resolution on {len(missing_fields)} fields reduces certainty."
        else:
            conf_summary += " with full resolution."

        headline = "Prime Acquisition Target" if score >= 80 else ("Distressed Opportunity" if score >= 50 else "Latent Signal")
        if coverage < 0.6:
            headline += " — High Uncertainty"

        return {
            "headline": headline,
            "decision_label": action,
            "drivers": drivers,
            "blockers": blockers,
            "confidence_summary": conf_summary
        }
