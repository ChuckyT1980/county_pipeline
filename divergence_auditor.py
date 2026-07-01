import json
from calibration import run_dual
from tests.test_gold import gold_records
from canonical import init_intelligence_record
from signals import generate_signals

def compute_tdi(results):
    drift_count = sum(1 for r in results if r["fr0"]["tier"] != r["fr1"]["tier"])
    return drift_count / len(results) if results else 0

def compute_dsb(results):
    deltas = [r["fr1"]["opportunity_score"] - r["fr0"]["opportunity_score"] for r in results]
    return sum(deltas) / len(deltas) if deltas else 0

def compute_ccr(results):
    ratios = []
    for r in results:
        fr0_conf = r["fr0"]["confidence"]
        fr1_conf = r["fr1"]["confidence"]
        if fr0_conf > 0:
            ratios.append(fr1_conf / fr0_conf)
        else:
            ratios.append(1.0)
    return sum(ratios) / len(ratios) if ratios else 1.0

def compute_ssi(results, raw_data):
    # Need to re-run the pipeline to get the boolean signals for FR-0 and FR-1
    # since calibration.py didn't return them directly.
    stable_signals = 0
    
    for idx, r in enumerate(results):
        raw = raw_data[idx]
        
        # Run FR-0
        rec_fr0 = init_intelligence_record(raw, raw.get("county", "unknown"), use_fr1=False)
        generate_signals(rec_fr0)
        
        # Run FR-1
        rec_fr1 = init_intelligence_record(raw, raw.get("county", "unknown"), use_fr1=True)
        generate_signals(rec_fr1)
        
        # Compare key signals
        stable = True
        for attr in ["deceased_owner", "trust_owner", "out_of_state_owner"]:
            if getattr(rec_fr0.signals, attr) != getattr(rec_fr1.signals, attr):
                stable = False
                break
                
        if stable:
            stable_signals += 1
            
    return stable_signals / len(results) if results else 1.0

def classify(metrics):
    if metrics["tier_drift"] < 0.1:
        return "INERT (FR-1 effectively not functioning)"
    if metrics["tier_drift"] > 0.3:
        return "DISRUPTIVE (FR-1 breaking scoring stability)"
    if metrics["confidence_ratio"] < 0.7:
        return "REACTIVE (healthy correction layer)"
    return "STABLE (FR-1 behaving as a refinement layer)"

from scoring import process_record

def run_auditor():
    raw_data = [item["layer_1_facts"] for item in gold_records]
    results = []
    
    for raw in raw_data:
        # Run FR-0
        rec_fr0 = init_intelligence_record(raw, raw.get("county", "unknown"), use_fr1=False)
        generate_signals(rec_fr0)
        process_record(rec_fr0)
        
        # Run FR-1
        rec_fr1 = init_intelligence_record(raw, raw.get("county", "unknown"), use_fr1=True)
        generate_signals(rec_fr1)
        process_record(rec_fr1)
        
        results.append({
            "apn": raw.get("apn", "unknown"),
            "fr0": {
                "tier": rec_fr0.opportunity.tier,
                "opportunity_score": rec_fr0.opportunity.attractiveness_score,
                "confidence": rec_fr0.confidence.overall_confidence
            },
            "fr1": {
                "tier": rec_fr1.opportunity.tier,
                "opportunity_score": rec_fr1.opportunity.attractiveness_score,
                "confidence": rec_fr1.confidence.overall_confidence
            }
        })
        
    metrics = {
        "tier_drift": compute_tdi(results),
        "bias": compute_dsb(results),
        "confidence_ratio": compute_ccr(results),
        "signal_stability": compute_ssi(results, raw_data)
    }
    
    classification = classify(metrics)
    
    report = f"""## FR-1 Divergence Summary

- Tier Drift Index: {metrics['tier_drift']:.2f}
- Directional Bias: {metrics['bias']:.2f}
- Confidence Compression: {metrics['confidence_ratio']:.2f}
- Signal Stability: {metrics['signal_stability']:.2f}

Classification: {classification}
"""
    
    print(report)
    with open("snapshots/divergence_report.md", "w") as f:
        f.write(report)
        f.write("\n## Per-Record Outputs\n```json\n")
        f.write(json.dumps(results, indent=2))
        f.write("\n```\n")
        
    return results, metrics

if __name__ == "__main__":
    run_auditor()
