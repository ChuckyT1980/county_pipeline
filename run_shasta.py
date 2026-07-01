import json
from canonical import init_intelligence_record
from signals import generate_signals
from scoring import process_record
from fwc import compute_fr1_weight
from divergence_auditor import compute_tdi, compute_dsb, compute_ccr, compute_ssi, classify

def run_shasta_pipeline():
    with open("data/raw/shasta_live.jsonl") as f:
        raw_data = [json.loads(line) for line in f]
        
    results = []
    
    for raw in raw_data:
        # Run FR-0
        rec_fr0 = init_intelligence_record(raw, raw.get("county", "shasta"), use_fr1=False)
        generate_signals(rec_fr0)
        process_record(rec_fr0)
        
        # Run FR-1
        rec_fr1 = init_intelligence_record(raw, raw.get("county", "shasta"), use_fr1=True)
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
        
        # Print expected output tracing for each record
        print(f"\n--- APN {raw['apn']} ---")
        print(f"FR-0 -> Tier: {rec_fr0.opportunity.tier} | Score: {rec_fr0.opportunity.attractiveness_score:.2f} | Conf: {rec_fr0.confidence.overall_confidence:.2f}")
        print(f"FR-1 -> Tier: {rec_fr1.opportunity.tier} | Score: {rec_fr1.opportunity.attractiveness_score:.2f} | Conf: {rec_fr1.confidence.overall_confidence:.2f}")
        
    metrics = {
        "tier_drift": compute_tdi(results),
        "bias": compute_dsb(results),
        "confidence_ratio": compute_ccr(results),
        "signal_stability": compute_ssi(results, raw_data)
    }
    
    classification = classify(metrics)
    
    report = f"""\n## SHASTA LIVE DIVERGENCE SUMMARY

- Tier Drift Index: {metrics['tier_drift']:.2f}
- Directional Bias: {metrics['bias']:.2f}
- Confidence Compression: {metrics['confidence_ratio']:.2f}
- Signal Stability: {metrics['signal_stability']:.2f}

Classification: {classification}
"""
    print(report)

if __name__ == "__main__":
    run_shasta_pipeline()
