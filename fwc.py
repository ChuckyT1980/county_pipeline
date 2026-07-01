def compute_fr1_weight(profile, stress_results=None):
    """
    Computes the final fr1_weight for a county based on drift profile and stress fragility.
    """
    base = 0.6
    
    # Adjust for noise (messy county = rely on FR-1 more to filter)
    base += profile.get("noise_index", 0.0) * 0.3
    
    # Adjust for fragility (if FR-1 breaks easily, rely on it less)
    if stress_results:
        base -= stress_results.get("fragility_index", 0.0) * 0.4
    
    # Adjust for calibration risk (if FR-1 kills too many good deals, rely on it less)
    base -= profile.get("over_filtering_rate", 0.0) * 0.5
    
    return max(0.1, min(1.0, base))

if __name__ == "__main__":
    from county_profiler import run_county_pipeline
    from tests.test_gold import gold_records
    from stress_test import run_stress_suite, generate_stress_report
    import random
    import json
    
    county_data = [item["layer_1_facts"] for item in gold_records]
    
    # 1. Run County Profiler
    _, profile, decision = run_county_pipeline(county_data)
    
    # 2. Run Stress Test
    # For testing, we just use the gold_records
    # In reality, stress test might run periodically
    random.seed(42)
    stress_outputs = run_stress_suite(county_data)
    stress_metrics = generate_stress_report(stress_outputs)
    
    # 3. Compute Weight
    weight = compute_fr1_weight(profile, stress_metrics)
    
    print("\n# FWC-1 Controller Output")
    print(json.dumps({
        "county_profile": profile,
        "stress_metrics": stress_metrics,
        "decision": decision,
        "computed_fr1_weight": weight
    }, indent=2))
