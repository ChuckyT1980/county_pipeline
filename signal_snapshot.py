"""
SIGNAL SNAPSHOT EMITTER — frozen feature vector log per scoring run.

After scoring.py assigns opportunity_score, call:
    emit_signal_snapshot(canonical, run_id)

This writes to logs/signal_snapshots.jsonl — the linkage between
"what signals existed" and "what outcomes later occurred."

Without this, CPS-1 learning only knows outcomes. With this, it can
answer: "which signals predicted those outcomes?"

This file is APPEND-ONLY. Never rewrite existing snapshots.
"""

import json
import os
from datetime import datetime, timezone

SNAPSHOTS_FILE = os.path.join("logs", "signal_snapshots.jsonl")


def emit_signal_snapshot(canonical: dict, run_id: str) -> dict:
    """
    Freeze the signal state and score for one APN at scoring time.

    Reads directly from the canonical object produced by scoring.py,
    so no transformation is needed. Just call this immediately after
    score() returns.

    Args:
        canonical:  The fully scored canonical dict (from scoring.py output)
        run_id:     The pipeline run identifier (e.g. "pipeline_run_20260624_001")

    Returns:
        The snapshot dict that was written.
    """
    apn = canonical.get("apn") or "UNKNOWN"

    # Flatten signals into a boolean map — what was TRUE for this APN?
    ownership  = canonical.get("signals", {}).get("ownership_friction", [])
    time_press = canonical.get("signals", {}).get("time_pressure", [])

    signal_map = {
        # Ownership friction signals
        "deceased_owner":    "deceased_owner"    in ownership,
        "trust_entity":      "trust_entity"      in ownership,
        "multiple_parties":  "multiple_parties"  in ownership,

        # Time pressure signals
        "time_high":         "high"     in time_press,
        "time_moderate":     "moderate" in time_press,
        "time_low":          "low"      in time_press,

        # Derived quality signal — does this APN have a valid APN at all?
        "has_valid_apn":     bool(canonical.get("apn")),
    }

    snapshot = {
        "apn":       apn,
        "county":    canonical.get("county", ""),
        "run_id":    run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signals":   signal_map,
        "score":     canonical.get("derived_scores", {}).get("opportunity_score", 0),
        "tier":      canonical.get("tier", ""),
    }

    os.makedirs("logs", exist_ok=True)
    with open(SNAPSHOTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot) + "\n")

    return snapshot


def load_snapshots_for_run(run_id: str) -> list:
    """Return all signal snapshots for a specific pipeline run."""
    snapshots = []
    if not os.path.exists(SNAPSHOTS_FILE):
        return snapshots
    with open(SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                if row.get("run_id") == run_id:
                    snapshots.append(row)
    return snapshots


def load_snapshot_for_apn(apn: str) -> list:
    """
    Return all historical snapshots for a single APN (across all runs).
    Returns newest-first so the most recent scoring run is index 0.
    """
    snapshots = []
    if not os.path.exists(SNAPSHOTS_FILE):
        return snapshots
    with open(SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                if row.get("apn") == apn:
                    snapshots.append(row)
    return sorted(snapshots, key=lambda x: x.get("timestamp", ""), reverse=True)


def load_all_snapshots() -> list:
    """Return every signal snapshot ever written."""
    snapshots = []
    if not os.path.exists(SNAPSHOTS_FILE):
        return snapshots
    with open(SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                snapshots.append(json.loads(line))
    return snapshots
