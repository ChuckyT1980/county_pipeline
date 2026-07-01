from calibration import run_dual
from canonical import init_intelligence_record

def evaluate_county(profile):
    opr = profile["opportunity_preservation_rate"]
    ofi = profile["over_filtering_rate"]
    noise = profile["noise_index"]
    
    if opr >= 0.90 and ofi <= 0.10:
        return "PASS"
    elif opr < 0.80 or ofi > 0.20:
        return "FAIL"
    else:
        # Check quarantine thresholds
        if (0.80 <= opr < 0.90) or noise > 0.6:
            return "QUARANTINE"
        # Edge cases fall to Quarantine to be safe
        return "QUARANTINE"

def build_county_profile(results, county_data):
    conflict_count = 0
    total_fields = 0
    
    # Calculate OPR and OFI
    high_intent_records = [r for r in results if r["proxy_label"] == "HIGH_INTENT"]
    if high_intent_records:
        preserved = sum(1 for r in high_intent_records if r["fr1"]["decision"] in ["HIGH_INTENT", "EXPLORATORY_INTENT"])
        opr = preserved / len(high_intent_records)
        killed = sum(1 for r in high_intent_records if r["fr1"]["decision"] == "NO_INTENT")
        ofi = killed / len(high_intent_records)
    else:
        opr = 1.0
        ofi = 0.0

    # Calculate conflict rate and sensitivity
    total_sensitivity = 0.0
    for idx, r in enumerate(results):
        raw_record = county_data[idx]
        record = init_intelligence_record(raw_record, raw_record.get("county", "unknown"), use_fr1=True)
        for field in [record.facts.owner, record.facts.mailing_address, record.facts.situs_address, record.facts.land_use]:
            total_fields += 1
            if field.state in ["PARTIAL_CONFLICT", "CONFLICTED"]:
                conflict_count += 1
                
        total_sensitivity += abs(r["baseline"]["score"] - r["fr1"]["score"])

    conflict_rate = conflict_count / total_fields if total_fields else 0
    missing_fields_rate = 0.1 # Placeholder: easily derived in real ingestion
    noise_index = (conflict_rate * 0.6) + (missing_fields_rate * 0.4)
    avg_sensitivity = total_sensitivity / len(results) if results else 0
    
    return {
        "county": results[0].get("county", "unknown") if results else "unknown",
        "conflict_rate": conflict_rate,
        "opportunity_preservation_rate": opr,
        "over_filtering_rate": ofi,
        "noise_index": noise_index,
        "avg_sensitivity": avg_sensitivity
    }

def run_county_pipeline(county_data):
    # Pass county_data through calibration dual runner to get baseline + fr1 results
    results = []
    
    # Needs a mock proxy label mapping
    from calibration import get_proxy_label
    for raw in county_data:
        raw["proxy_label"] = get_proxy_label(raw)
        results.append(run_dual(raw))
        
    profile = build_county_profile(results, county_data)
    decision = evaluate_county(profile)

    final_records = []
    for raw in county_data:
        # Generate the final canonical record (using FR1 as intended)
        record = init_intelligence_record(raw, raw.get("county", "unknown"), use_fr1=True)
        if decision == "QUARANTINE":
            record.metadata["county_state"] = "QUARANTINE"
            record.metadata["fr1_weight_multiplier"] = 0.7
        elif decision == "PASS":
            record.metadata["county_state"] = "PASS"
            record.metadata["fr1_weight_multiplier"] = 1.0
        else:
            record.metadata["county_state"] = "FAIL"
            # If fail, maybe we don't process or flag heavily
            record.metadata["fr1_weight_multiplier"] = 0.0

        final_records.append(record)

    return final_records, profile, decision

if __name__ == "__main__":
    from tests.test_gold import gold_records
    county_data = [item["layer_1_facts"] for item in gold_records]
    final_records, profile, decision = run_county_pipeline(county_data)
    print("County Profile:")
    import json
    print(json.dumps(profile, indent=2))
    print("Decision:", decision)
