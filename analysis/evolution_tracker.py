import os
import json
import sys
from datetime import datetime

LEDGER_PATH = "drift_ledger.jsonl"
ORDER = ["API", "PARSE", "FLOAT", "LOGIC", "ORDERING"]

def vectorize(summary: dict) -> list:
    return [summary.get(k, 0) for k in ORDER]

def track_evolution(run_id: str):
    replay_dir = os.path.join("replays", run_id)
    report_path = os.path.join(replay_dir, "drift_report.json")
    
    if not os.path.exists(report_path):
        raise FileNotFoundError(f"No drift report found for run {run_id}. Must execute drift_engine first.")
        
    with open(report_path, "r") as f:
        drift_data = json.load(f)
        
    summary = drift_data.get("drift_summary", {})
    vector = vectorize(summary)
    total_drift = sum(vector)
    
    ratio = {k: (summary.get(k, 0) / total_drift if total_drift > 0 else 0) for k in ORDER}
    
    # Read ledger for previous run
    previous_run_id = None
    previous_vector = [0, 0, 0, 0, 0]
    
    if os.path.exists(LEDGER_PATH):
        with open(LEDGER_PATH, "r") as f:
            lines = f.readlines()
            if lines:
                last_entry = json.loads(lines[-1])
                previous_run_id = last_entry["run_id"]
                previous_vector = vectorize(last_entry["drift_summary"])
                
    delta = [v - p for v, p in zip(vector, previous_vector)]
    total_delta = sum(delta)
    
    if previous_run_id is None:
        trend = "INITIAL"
    elif total_delta < 0:
        trend = "STABILIZING"
    elif total_delta > 0:
        trend = "DEGRADING"
    else:
        trend = "UNCHANGED"
        
    evolution_report = {
        "run_id": run_id,
        "previous_run_id": previous_run_id,
        "total_drift": total_drift,
        "delta": delta,
        "trend": trend,
        "ratio": ratio
    }
    
    evo_path = os.path.join(replay_dir, "drift_evolution_report.json")
    with open(evo_path, "w") as f:
        json.dump(evolution_report, f, indent=4)
        
    # Append to ledger (immutable timeline)
    ledger_entry = {
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "drift_summary": summary,
        "total_drift": total_drift
    }
    
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(ledger_entry) + "\n")
        
    print(f"\n[EVOLUTION TRACKING COMPLETE]")
    print(f"Run: {run_id}")
    print(f"Trend: {trend}")
    print(f"Total Drift: {total_drift} (Delta: {total_delta})")
    print(f"Report saved to: {evo_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evolution_tracker.py <run_id>")
        sys.exit(1)
    track_evolution(sys.argv[1])
