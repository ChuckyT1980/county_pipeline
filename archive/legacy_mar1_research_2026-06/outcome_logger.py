"""
OUTCOME LOGGER — Ground-truth ledger for APN-level interaction history.

Two responsibilities:
  1. log_outcome()      → write one interaction event to logs/outcomes.jsonl
  2. get_apn_state()    → compute the derived APN outcome aggregation view

This file does NOT touch scoring, parsing, signals, or weights.
It is a pure append-only ledger + materialized view builder.

Outcome states (progression order):
  no_contact → contact_made → interested → not_interested
                                         → deal_started → deal_closed
"""

import json
import os
from datetime import datetime, timezone

OUTCOMES_FILE = os.path.join("logs", "outcomes.jsonl")
APN_STATE_FILE = os.path.join("logs", "apn_outcome_state.jsonl")

# Ordered rank so we always track the "best" result reached
OUTCOME_RANK = {
    "no_contact":      0,
    "contact_made":    1,
    "not_interested":  2,
    "interested":      3,
    "deal_started":    4,
    "deal_closed":     5,
}

VALID_INTERACTION_TYPES = {"call", "mail", "email", "lookup", "visit"}
VALID_RESULTS = set(OUTCOME_RANK.keys())


def log_outcome(
    apn: str,
    county: str,
    interaction_type: str,
    result: str,
    run_id: str = "",
    notes: str = "",
) -> dict:
    """
    Append one interaction event to logs/outcomes.jsonl.

    Args:
        apn:              Property APN  (e.g. "049-040-021-000")
        county:           County slug   (e.g. "shasta")
        interaction_type: One of call | mail | email | lookup | visit
        result:           One of the six progression states
        run_id:           Optional — pipeline run that generated this lead
        notes:            Optional free text

    Returns:
        The event dict that was written (for caller convenience).
    """
    if interaction_type not in VALID_INTERACTION_TYPES:
        raise ValueError(
            f"Invalid interaction_type '{interaction_type}'. "
            f"Must be one of: {VALID_INTERACTION_TYPES}"
        )
    if result not in VALID_RESULTS:
        raise ValueError(
            f"Invalid result '{result}'. "
            f"Must be one of: {VALID_RESULTS}"
        )

    event = {
        "apn":              apn,
        "county":           county,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "interaction_type": interaction_type,
        "result":           result,
        "notes":            notes,
        "related_run_id":   run_id,
    }

    os.makedirs("logs", exist_ok=True)
    with open(OUTCOMES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    # Rebuild the APN's aggregated state every time an event is logged
    _rebuild_apn_state(apn, county)

    print(
        f"[OUTCOME] {apn} | {interaction_type.upper()} | {result.upper()}"
        + (f" | {notes[:60]}" if notes else "")
    )
    return event


def get_apn_state(apn: str) -> dict | None:
    """
    Return the current aggregated state for a single APN.
    Reads from the materialized apn_outcome_state.jsonl ledger.
    Returns None if the APN has no logged interactions yet.
    """
    if not os.path.exists(APN_STATE_FILE):
        return None
    with open(APN_STATE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                if row.get("apn") == apn:
                    return row
    return None


def _rebuild_apn_state(apn: str, county: str) -> None:
    """
    Recompute and persist the APN's aggregated outcome view.

    Reads ALL events for this APN from outcomes.jsonl,
    collapses into a single state row, and upserts it into
    apn_outcome_state.jsonl.
    """
    events = _load_events_for_apn(apn)
    if not events:
        return

    touch_count = len(events)
    best_result = max(events, key=lambda e: OUTCOME_RANK.get(e["result"], -1))["result"]
    last_event  = max(events, key=lambda e: e["timestamp"])

    # Derive a human-readable pipeline state
    if best_result == "deal_closed":
        final_state = "closed"
    elif best_result == "deal_started":
        final_state = "active_pipeline"
    elif best_result == "interested":
        final_state = "warm_lead"
    elif best_result == "contact_made":
        final_state = "contacted"
    elif best_result == "not_interested":
        final_state = "dead"
    else:
        final_state = "attempted"

    new_row = {
        "apn":               apn,
        "county":            county,
        "total_touch_count": touch_count,
        "best_result":       best_result,
        "final_state":       final_state,
        "last_interaction":  last_event["timestamp"],
    }

    # Upsert: rewrite the state file replacing this APN's row
    rows = []
    replaced = False
    if os.path.exists(APN_STATE_FILE):
        with open(APN_STATE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("apn") == apn:
                    rows.append(new_row)
                    replaced = True
                else:
                    rows.append(row)

    if not replaced:
        rows.append(new_row)

    with open(APN_STATE_FILE, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _load_events_for_apn(apn: str) -> list:
    """Return all outcome events for a given APN from the ledger."""
    events = []
    if not os.path.exists(OUTCOMES_FILE):
        return events
    with open(OUTCOMES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                event = json.loads(line)
                if event.get("apn") == apn:
                    events.append(event)
    return events


def load_all_outcomes() -> list:
    """Return the full outcomes ledger as a list of event dicts."""
    events = []
    if not os.path.exists(OUTCOMES_FILE):
        return events
    with open(OUTCOMES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def load_all_apn_states() -> list:
    """Return the full APN outcome aggregation view."""
    rows = []
    if not os.path.exists(APN_STATE_FILE):
        return rows
    with open(APN_STATE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ──────────────────────────────────────────────
# CLI convenience — log an outcome from the terminal:
#   python outcome_logger.py 049-040-021-000 shasta call interested "They called back"
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print("Usage: python outcome_logger.py <apn> <county> <interaction_type> <result> [notes] [run_id]")
        print("  interaction_type: call | mail | email | lookup | visit")
        print("  result:           no_contact | contact_made | interested | not_interested | deal_started | deal_closed")
        sys.exit(1)

    log_outcome(
        apn              = sys.argv[1],
        county           = sys.argv[2],
        interaction_type = sys.argv[3],
        result           = sys.argv[4],
        notes            = sys.argv[5] if len(sys.argv) > 5 else "",
        run_id           = sys.argv[6] if len(sys.argv) > 6 else "",
    )
