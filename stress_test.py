import random
import copy
import json
from calibration import run_dual

def drop_source(record, field):
    r = copy.deepcopy(record)
    if field in r and isinstance(r[field], dict):
        keys = list(r[field].keys())
        if keys:
            k = random.choice(keys)
            r[field].pop(k)
    return r

def corrupt_string(value):
    if not value:
        return value
    noise = ["  ", ".", "-", "??", "#", "  "]
    return value + random.choice(noise)

def swap_owner_parts(record):
    r = copy.deepcopy(record)
    if "owner_sources" in r:
        vals = list(r["owner_sources"].values())
        random.shuffle(vals)
        keys = list(r["owner_sources"].keys())
        r["owner_sources"] = dict(zip(keys, vals))
    return r

def inject_nulls(record, rate=0.2):
    r = copy.deepcopy(record)
    for k in r.get("owner_sources", {}):
        if random.random() < rate:
            r["owner_sources"][k] = None
    return r

def generate_variants(record):
    return [
        drop_source(record, "owner_sources"),
        swap_owner_parts(record),
        inject_nulls(record, 0.3),
        record,  # baseline control
    ]

def run_stress_suite(gold_set):
    results = []
    for record in gold_set:
        variants = generate_variants(record)
        for v in variants:
            output = run_dual(v)
            results.append({
                "apn": record.get("apn", "unknown"),
                "variant_type": "control" if v is record else "corrupted",
                "baseline": output["baseline"]["decision"],
                "fr1": output["fr1"]["decision"],
                "baseline_score": output["baseline"]["score"],
                "fr1_score": output["fr1"]["score"]
            })
    return results

def compute_volatility(results):
    flips = 0
    for r in results:
        if r["baseline"] != r["fr1"]:
            flips += 1
    return flips / len(results) if results else 0

def compute_sensitivity(results):
    deltas = []
    for r in results:
        deltas.append(abs(r["fr1_score"] - r["baseline_score"]))
    return sum(deltas) / len(deltas) if deltas else 0

def compute_stability(results):
    stable = 0
    for r in results:
        if r["fr1"] in ["HIGH_INTENT", "EXPLORATORY_INTENT"]:
            stable += 1
    return stable / len(results) if results else 0

def generate_stress_report(results):
    volatility = compute_volatility(results)
    sensitivity = compute_sensitivity(results)
    stability = compute_stability(results)
    
    print("# FR-1 Stress Test Report\n")
    print(f"Tier Volatility: {volatility:.2f}")
    print(f"FR-1 Sensitivity: {sensitivity:.2f}")
    print(f"Stability Score: {stability:.2f}\n")
    
    print("Sample results:")
    for r in results[:10]:
        print(r)
        
    return {
        "tier_volatility": volatility,
        "sensitivity_index": sensitivity,
        "stability_score": stability,
        "fragility_index": volatility # Mapping volatility as fragility for FWC-1
    }

if __name__ == "__main__":
    from tests.test_gold import gold_records
    # Need proxy labels assigned just like calibration does
    from calibration import get_proxy_label
    
    gold_set = []
    for item in gold_records:
        raw = item["layer_1_facts"]
        raw["proxy_label"] = get_proxy_label(raw)
        gold_set.append(raw)
        
    random.seed(42) # For reproducible stress test in dev
    results = run_stress_suite(gold_set)
    generate_stress_report(results)
