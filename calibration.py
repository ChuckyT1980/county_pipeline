import json
from canonical import init_intelligence_record
from signals import generate_signals
from scoring import process_record

def to_decision(tier: int) -> str:
    if tier in [0, 1]:
        return "HIGH_INTENT"
    elif tier == 2:
        return "EXPLORATORY_INTENT"
    elif tier == 3:
        return "UNCERTAIN_INTENT"
    else:
        return "NO_INTENT"

def compute_alignment(results):
    baseline_match_count = sum(1 for r in results if r["baseline"]["decision"] == r["proxy_label"])
    fr1_match_count = sum(1 for r in results if r["fr1"]["decision"] == r["proxy_label"])
    
    baseline_alignment = baseline_match_count / len(results) if results else 0
    fr1_alignment = fr1_match_count / len(results) if results else 0
    return fr1_alignment - baseline_alignment

def compute_opi(results):
    high_intent_records = [r for r in results if r["proxy_label"] == "HIGH_INTENT"]
    if not high_intent_records:
        return 1.0
        
    preserved = sum(1 for r in high_intent_records if r["fr1"]["decision"] in ["HIGH_INTENT", "EXPLORATORY_INTENT"])
    return preserved / len(high_intent_records)

def compute_ofi(results):
    high_intent_records = [r for r in results if r["proxy_label"] == "HIGH_INTENT"]
    if not high_intent_records:
        return 0.0
        
    killed = sum(1 for r in high_intent_records if r["fr1"]["decision"] == "NO_INTENT")
    return killed / len(high_intent_records)

def compute_avg_delta(results):
    if not results: return 0.0
    deltas = [r["fr1"]["score"] - r["baseline"]["score"] for r in results]
    return sum(deltas) / len(deltas)

def run_baseline(raw_record):
    record = init_intelligence_record(raw_record, raw_record.get("county", "unknown"), use_fr1=False)
    generate_signals(record)
    process_record(record)
    return {
        "tier": record.opportunity.tier,
        "score": record.opportunity.attractiveness_score,
        "decision": to_decision(record.opportunity.tier),
        "explanation": record.opportunity.record_explanation
    }

def run_fr1(raw_record):
    record = init_intelligence_record(raw_record, raw_record.get("county", "unknown"), use_fr1=True)
    generate_signals(record)
    process_record(record)
    return {
        "tier": record.opportunity.tier,
        "score": record.opportunity.attractiveness_score,
        "decision": to_decision(record.opportunity.tier),
        "explanation": record.opportunity.record_explanation,
        "avg_confidence": sum([
            record.facts.owner.confidence, 
            record.facts.mailing_address.confidence,
            record.facts.situs_address.confidence
        ]) / 3.0
    }

def run_dual(raw_record):
    base = run_baseline(raw_record)
    fr1 = run_fr1(raw_record)
    return {
        "apn": raw_record.get("apn", "unknown"),
        "proxy_label": raw_record["proxy_label"],
        "baseline": base,
        "fr1": fr1
    }

def generate_dashboard(results):
    with open("snapshots/calibration_dashboard.md", "w") as f:
        f.write("# FR-1 Calibration Report\n\n")
        f.write("## Summary Metrics\n")
        f.write(f"- **alignment_delta**: {compute_alignment(results):.2f}\n")
        f.write(f"- **Opportunity Preservation Index (OPI)**: {compute_opi(results):.0%}\n")
        f.write(f"- **Over-Filtering Index (OFI)**: {compute_ofi(results):.0%}\n")
        f.write(f"- **avg_delta**: {compute_avg_delta(results):.2f}\n\n")
        
        f.write("## Per-record breakdown\n\n")
        for r in results:
            delta_score = r["fr1"]["score"] - r["baseline"]["score"]
            f.write(f"### APN: {r['apn']}\n")
            f.write(f"- **Proxy Label**: {r['proxy_label']}\n")
            f.write(f"- **Baseline Decision**: {r['baseline']['decision']} (Tier {r['baseline']['tier']}, Score: {r['baseline']['score']:.2f})\n")
            f.write(f"- **FR-1 Decision**: {r['fr1']['decision']} (Tier {r['fr1']['tier']}, Score: {r['fr1']['score']:.2f})\n")
            f.write(f"- **Score Delta**: {delta_score:+.2f}\n")
            f.write(f"- **FR-1 Explanation**: {r['fr1']['explanation']}\n\n")

def get_proxy_label(raw):
    # We need a quick heuristic as specified by the user
    record = init_intelligence_record(raw, raw.get("county", "unknown"), use_fr1=False)
    generate_signals(record)
    from scoring import generate_states
    generate_states(record)
    
    comp = record.states.ownership_complexity
    tax = record.states.tax_pressure
    util = record.states.property_utility_score
    dec = record.signals.deceased_owner
    
    if (comp >= 0.4 or dec) and tax >= 0.1 and util >= 0.5:
        return "HIGH_INTENT"
    elif util >= 0.7 and (comp >= 0.3 or tax >= 0.05):
        return "EXPLORATORY_INTENT"
    elif util < 0.3 or (tax < 0.05 and record.signals.owner_occupied):
        return "NO_INTENT"
    else:
        return "UNCERTAIN_INTENT"

if __name__ == "__main__":
    from tests.test_gold import gold_records
    
    # Define the proxy labels manually for the 5 records based on deterministic logic
    # Record 1 (Estate / High Distress / Low Value Trap)
    gold_records[0]["layer_1_facts"]["proxy_label"] = "NO_INTENT"
    
    # Record 2 (High Value / Low Distress / False Positive Trap -> Wait, this is a Trust, so it's a potential equity play)
    gold_records[1]["layer_1_facts"]["proxy_label"] = "EXPLORATORY_INTENT"
    
    # Record 3 (Trust / Moderate Distress / Medium Value)
    gold_records[2]["layer_1_facts"]["proxy_label"] = "HIGH_INTENT" # Wait, moderate distress, let's say EXPLORATORY or HIGH
    
    for item in gold_records:
        item["layer_1_facts"]["proxy_label"] = get_proxy_label(item["layer_1_facts"])

    results = []
    for item in gold_records:
        r = run_dual(item["layer_1_facts"])
        results.append(r)
        
    import os
    if not os.path.exists("snapshots"):
        os.makedirs("snapshots")
        
    generate_dashboard(results)
    print("Calibration Dashboard generated at snapshots/calibration_dashboard.md")
