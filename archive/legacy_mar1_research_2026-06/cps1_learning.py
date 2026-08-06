"""
CPS-1 LEARNING ENGINE
Reads deal_tracker.jsonl outcomes and computes real signal-to-conversion rates.
Suggests updated scoring weights based on actual buyer behavior.
NEVER touches parsing, extraction, or canonical building.
"""
import json
from collections import defaultdict

TRACKER_FILE = "deal_tracker.jsonl"
WEIGHTS_FILE = "cps1_weights.json"

POSITIVE_OUTCOMES = {"responded", "interested", "deal", "high_interest", "sample_request"}


def load_tracker():
    records = []
    try:
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except FileNotFoundError:
        pass
    return records


def extract_signals(record):
    """Flatten all signal buckets into a list of namespaced strings."""
    signals = []
    for s in record.get("signals", {}).get("ownership_friction", []):
        signals.append(f"ownership:{s}")
    for s in record.get("signals", {}).get("time_pressure", []):
        signals.append(f"time:{s}")
    return signals


def compute_signal_effectiveness(records):
    stats = defaultdict(lambda: {"seen": 0, "positive": 0})

    for r in records:
        outcome = r.get("outcome", r.get("response_type", "ignored"))
        is_positive = outcome in POSITIVE_OUTCOMES

        for s in extract_signals(r):
            stats[s]["seen"] += 1
            if is_positive:
                stats[s]["positive"] += 1

    results = {}
    for signal, data in stats.items():
        if data["seen"] > 0:
            results[signal] = {
                "conversion_rate": round(data["positive"] / data["seen"], 3),
                "volume":          data["seen"],
            }

    return dict(sorted(results.items(), key=lambda x: x[1]["conversion_rate"], reverse=True))


def suggest_weight_updates(signal_stats):
    """Scale current weights by observed conversion rates."""
    try:
        with open(WEIGHTS_FILE, "r") as f:
            current = json.load(f)
    except FileNotFoundError:
        current = {}

    suggestions = {}
    for signal, data in signal_stats.items():
        key = signal.split(":")[-1]  # strip namespace
        if key in current:
            adjusted = round(current[key] * (0.5 + data["conversion_rate"]), 1)
            suggestions[key] = {"current": current[key], "suggested": adjusted, "based_on": data}

    return suggestions


def run_learning_cycle():
    records = load_tracker()
    if not records:
        print("[CPS-1] No outcome data yet. Log buyer responses via deal_tracker.py first.")
        return

    print(f"[CPS-1] Analyzing {len(records)} tracked interactions...\n")

    effectiveness = compute_signal_effectiveness(records)

    print("=== SIGNAL EFFECTIVENESS ===")
    for signal, data in effectiveness.items():
        bar = "█" * int(data["conversion_rate"] * 20)
        print(f"  {signal:<35} {bar:<20} {data['conversion_rate']*100:.0f}% ({data['volume']} samples)")

    suggestions = suggest_weight_updates(effectiveness)

    if suggestions:
        print("\n=== SUGGESTED WEIGHT UPDATES ===")
        for key, info in suggestions.items():
            direction = "▲" if info["suggested"] > info["current"] else "▼"
            print(f"  {key:<25} {info['current']} → {info['suggested']} {direction}")
    else:
        print("\n[CPS-1] Not enough matched signals to suggest weight updates yet.")


if __name__ == "__main__":
    run_learning_cycle()
