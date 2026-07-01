"""
CPS-1 LEARNING ENGINE v2 — Signal Attribution + Empirical Weight Calibration

This replaces the prior learning engine that only read deal_tracker.jsonl.

New data flow:
    signal_snapshots.jsonl   (what signals were present at scoring time)
  + outcomes.jsonl           (what actually happened when we contacted them)
  → JOIN on apn
  → compute lift per signal
  → suggest updated weights → operator applies or auto-applies

Key design decisions:
  - Minimum support: n < 5 → signal is "untrusted," weight is NOT updated
  - Bayesian smoothing: adjusted_rate = (positives + 1) / (total + 2)
  - Temporal weighting: optional decay by recency (enable with --decay flag)
  - Weight update rule: new = old * 0.7 + learned_lift_normalized * 0.3
  - Weight constraints: always clamp to [0.2 * baseline, 3.0 * baseline]

Run manually:
    python cps1_learning_v2.py
    python cps1_learning_v2.py --apply          (writes to cps1_weights.json)
    python cps1_learning_v2.py --min-support 3  (lower threshold for small datasets)
    python cps1_learning_v2.py --decay 30       (30-day half-life)
"""

import json
import math
import sys
import os
from collections import defaultdict
from datetime import datetime, timezone

from signal_snapshot import load_all_snapshots
from outcome_logger  import load_all_outcomes, OUTCOME_RANK

WEIGHTS_FILE = "cps1_weights.json"

# Outcomes that count as "positive" for signal attribution
POSITIVE_OUTCOMES = {"interested", "deal_started", "deal_closed"}

# Outcomes that count as "negative" — explicit rejection, not just silence
NEGATIVE_OUTCOMES = {"not_interested"}

# Everything else (no_contact, contact_made) is "ignore" for lift computation
# because no_contact could mean bad phone number, not a bad lead.

# ── Defaults ────────────────────────────────────────────────────────────────
MIN_SUPPORT     = 5     # Never update a signal seen fewer than N times total
DECAY_DAYS      = None  # Set to integer (e.g. 30) to enable temporal weighting
BLEND_OLD       = 0.7   # How much the existing weight is preserved each cycle
BLEND_NEW       = 0.3   # How much learned lift contributes each cycle
WEIGHT_FLOOR    = 0.2   # Multiplier floor relative to baseline (prevents collapse)
WEIGHT_CEILING  = 3.0   # Multiplier ceiling relative to baseline (prevents runaway)


# ── Default baseline weights (mirrors cps1_weights.json defaults) ──────────
BASELINE_WEIGHTS = {
    "deceased_owner":   25,
    "trust_entity":     15,
    "multiple_parties": 10,
    "time_high":        25,
    "time_moderate":    15,
    "time_low":          5,
    "noise_penalty":   -20,
}


def load_current_weights() -> dict:
    try:
        with open(WEIGHTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return dict(BASELINE_WEIGHTS)


def _temporal_weight(timestamp_str: str, decay_days: int | None) -> float:
    """
    Returns a decay factor in (0, 1].
    If decay_days is None, returns 1.0 (no decay — all events equal weight).
    Uses exponential decay: w = exp(-days_elapsed / decay_days)
    """
    if decay_days is None:
        return 1.0
    try:
        ts = datetime.fromisoformat(timestamp_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - ts).days
        return math.exp(-elapsed / decay_days)
    except Exception:
        return 1.0


def build_join_table(snapshots: list, outcomes: list) -> dict:
    """
    Join signal snapshots to outcome events on APN.

    Returns a dict keyed by APN:
      {
        "apn": { "signals": {...}, "outcome_class": "positive|negative|ignore", "weight": float }
      }

    When an APN has MULTIPLE outcomes, we use the best one reached
    (highest OUTCOME_RANK). This prevents early no_contact events
    from poisoning a lead that later converted.
    """
    # Build outcome lookup: apn → best result
    outcome_by_apn: dict[str, dict] = {}
    for event in outcomes:
        apn = event.get("apn")
        if not apn:
            continue
        current_best = outcome_by_apn.get(apn)
        if current_best is None or (
            OUTCOME_RANK.get(event["result"], -1) > OUTCOME_RANK.get(current_best["result"], -1)
        ):
            outcome_by_apn[apn] = event

    # Build snapshot lookup: apn → most recent snapshot
    snapshot_by_apn: dict[str, dict] = {}
    for snap in sorted(snapshots, key=lambda x: x.get("timestamp", "")):
        apn = snap.get("apn")
        if apn:
            snapshot_by_apn[apn] = snap  # last write wins = most recent

    # Join
    joined = {}
    for apn, snap in snapshot_by_apn.items():
        if apn not in outcome_by_apn:
            continue  # No outcome recorded yet — skip

        event  = outcome_by_apn[apn]
        result = event.get("result", "no_contact")

        if result in POSITIVE_OUTCOMES:
            outcome_class = "positive"
        elif result in NEGATIVE_OUTCOMES:
            outcome_class = "negative"
        else:
            continue  # ignore class — don't count toward lift

        joined[apn] = {
            "signals":       snap.get("signals", {}),
            "outcome_class": outcome_class,
            "tw":            _temporal_weight(event.get("timestamp", ""), DECAY_DAYS),
        }

    return joined


def compute_signal_lift(joined: dict, min_support: int = MIN_SUPPORT) -> dict:
    """
    For each signal, compute:
      P(signal | positive)  — how often signal present in positive cases
      P(signal | negative)  — how often signal present in negative cases
      lift = P(pos) / P(neg), smoothed with Laplace (Bayesian) correction

    Returns dict keyed by signal name.
    """
    # Gather all signal keys from first available record
    all_signals = set()
    for row in joined.values():
        all_signals.update(row["signals"].keys())

    stats = {
        sig: {"pos": 0.0, "neg": 0.0, "pos_total": 0.0, "neg_total": 0.0}
        for sig in all_signals
    }

    pos_count = sum(1 for r in joined.values() if r["outcome_class"] == "positive")
    neg_count = sum(1 for r in joined.values() if r["outcome_class"] == "negative")

    for row in joined.values():
        tw  = row["tw"]
        cls = row["outcome_class"]
        for sig, present in row["signals"].items():
            if cls == "positive":
                stats[sig]["pos_total"] += tw
                if present:
                    stats[sig]["pos"] += tw
            elif cls == "negative":
                stats[sig]["neg_total"] += tw
                if present:
                    stats[sig]["neg"] += tw

    results = {}
    for sig, data in stats.items():
        total_seen = data["pos"] + data["neg"]

        # Minimum support gate — never trust tiny samples
        if total_seen < min_support:
            results[sig] = {
                "status":       "untrusted",
                "sample_size":  int(total_seen),
                "min_support":  min_support,
            }
            continue

        # Bayesian-smoothed rates
        pos_rate = (data["pos"] + 1) / (data["pos_total"] + 2) if data["pos_total"] > 0 else 0.5
        neg_rate = (data["neg"] + 1) / (data["neg_total"] + 2) if data["neg_total"] > 0 else 0.5

        lift = pos_rate / neg_rate if neg_rate > 0 else pos_rate * 2

        results[sig] = {
            "status":       "trusted",
            "pos_rate":     round(pos_rate,  3),
            "neg_rate":     round(neg_rate,  3),
            "lift":         round(lift,       3),
            "sample_size":  int(total_seen),
            "pos_count":    int(data["pos"]),
            "neg_count":    int(data["neg"]),
        }

    return results


def suggest_weight_updates(lift_results: dict, current_weights: dict) -> dict:
    """
    Apply the blended update rule:
        new_weight = old * BLEND_OLD + lift_normalized * BLEND_NEW

    lift_normalized: scales the lift into the same magnitude as current weights.
    Uses baseline weight as the reference scale, then clamps to [floor, ceiling].
    """
    suggestions = {}
    for sig, data in lift_results.items():
        if data.get("status") != "trusted":
            continue
        if sig not in current_weights:
            continue

        old_w     = current_weights[sig]
        baseline  = BASELINE_WEIGHTS.get(sig, old_w)
        lift      = data["lift"]

        # Normalize lift: lift=1.0 → baseline weight unchanged
        # lift=2.0 → suggest ~2x baseline, lift=0.5 → suggest ~0.5x baseline
        lift_scaled = baseline * lift

        # Blended update
        new_w = old_w * BLEND_OLD + lift_scaled * BLEND_NEW

        # Clamp to [floor, ceiling] relative to baseline
        new_w = max(baseline * WEIGHT_FLOOR, min(baseline * WEIGHT_CEILING, new_w))
        new_w = round(new_w, 1)

        suggestions[sig] = {
            "current":   old_w,
            "suggested": new_w,
            "lift":      data["lift"],
            "sample_n":  data["sample_size"],
            "direction": "▲" if new_w > old_w else ("▼" if new_w < old_w else "─"),
        }

    return suggestions


def apply_weight_updates(suggestions: dict, current_weights: dict) -> dict:
    """Write suggested weights back to cps1_weights.json."""
    updated = dict(current_weights)
    for sig, info in suggestions.items():
        updated[sig] = info["suggested"]

    with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)

    return updated


def run_learning_cycle(
    apply:       bool = False,
    min_support: int  = MIN_SUPPORT,
    decay_days:  int | None = DECAY_DAYS,
) -> dict:
    """
    Full learning cycle. Returns a summary dict for programmatic use.

    Args:
        apply:       If True, writes new weights to cps1_weights.json.
        min_support: Minimum number of observations before trusting a signal.
        decay_days:  Exponential decay half-life in days. None = no decay.
    """
    global DECAY_DAYS
    DECAY_DAYS = decay_days

    snapshots = load_all_snapshots()
    outcomes  = load_all_outcomes()

    print(f"\n[CPS-1 v2] Signal Attribution Learning Cycle")
    print(f"  Snapshots loaded : {len(snapshots)}")
    print(f"  Outcomes loaded  : {len(outcomes)}")

    if not snapshots:
        print("\n[!] No signal snapshots found.")
        print("    Run the pipeline first — snapshots are written automatically.")
        return {}

    if not outcomes:
        print("\n[!] No outcomes logged yet.")
        print("    Log interactions via: python outcome_logger.py <apn> <county> <type> <result>")
        return {}

    joined = build_join_table(snapshots, outcomes)
    print(f"  Joined APN pairs : {len(joined)} (snapshot & outcome)\n")

    if not joined:
        print("[!] No APNs found in both snapshots and outcomes.")
        print("    Check that your outcome APN strings match snapshot APN strings exactly.")
        return {}

    lift_results = compute_signal_lift(joined, min_support=min_support)
    current_weights = load_current_weights()
    suggestions = suggest_weight_updates(lift_results, current_weights)

    # ── Print signal effectiveness report ────────────────────────────────────
    print("═" * 65)
    print("  SIGNAL LIFT ANALYSIS")
    print("═" * 65)
    for sig, data in lift_results.items():
        if data.get("status") == "untrusted":
            print(f"  {sig:<30}  [UNTRUSTED] n={data['sample_size']} < {data['min_support']}")
        else:
            bar = "█" * min(20, int(data["lift"] * 5))
            print(
                f"  {sig:<30}  lift={data['lift']:.2f}  {bar:<20}  "
                f"pos={data['pos_rate']*100:.0f}%  neg={data['neg_rate']*100:.0f}%  "
                f"n={data['sample_size']}"
            )

    # ── Print weight update suggestions ──────────────────────────────────────
    print()
    if not suggestions:
        print("[CPS-1 v2] No updatable signals yet (none passed minimum support).")
        print(f"           Minimum support required: {min_support} samples per signal.")
    else:
        print("═" * 65)
        print("  WEIGHT UPDATE SUGGESTIONS")
        print("═" * 65)
        for sig, info in suggestions.items():
            print(
                f"  {sig:<25}  {info['current']:>6} → {info['suggested']:>6}  "
                f"{info['direction']}  (lift={info['lift']:.2f}, n={info['sample_n']})"
            )

        if apply:
            apply_weight_updates(suggestions, current_weights)
            print(f"\n[CPS-1 v2] ✓ Weights updated → {WEIGHTS_FILE}")
        else:
            print(f"\n[CPS-1 v2] Dry run — weights NOT written.")
            print(f"           Re-run with --apply to commit changes.")

    print()
    return {
        "snapshots":    len(snapshots),
        "outcomes":     len(outcomes),
        "joined_pairs": len(joined),
        "lift":         lift_results,
        "suggestions":  suggestions,
        "applied":      apply,
    }


if __name__ == "__main__":
    apply_flag   = "--apply"       in sys.argv
    decay_flag   = "--decay"       in sys.argv
    support_flag = "--min-support" in sys.argv

    decay_days = None
    if decay_flag:
        idx = sys.argv.index("--decay")
        try:
            decay_days = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("Usage: --decay <days>  (e.g. --decay 30)")
            sys.exit(1)

    min_support = MIN_SUPPORT
    if support_flag:
        idx = sys.argv.index("--min-support")
        try:
            min_support = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("Usage: --min-support <n>  (e.g. --min-support 3)")
            sys.exit(1)

    run_learning_cycle(apply=apply_flag, min_support=min_support, decay_days=decay_days)
