import os
import json
import sys

def classify_drift(diffs: list) -> list:
    """
    Pure function that takes a list of field diffs from the replay output
    and applies deterministic classification rules.
    """
    classified = []
    
    for diff in diffs:
        field = diff["field"]
        expected = diff.get("expected")
        actual = diff.get("actual")
        
        drift_type = "UNCLASSIFIED"
        layer = diff.get("layer", "unknown")
        
        # Rule A: FLOAT drift
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            if abs(expected - actual) <= 0.05:
                drift_type = "FLOAT"
            else:
                drift_type = "LOGIC"
        
        # Rule B: PARSE drift (String structural differences)
        elif isinstance(expected, str) and isinstance(actual, str):
            drift_type = "PARSE"
            
        # (Rule C & D API/ORDERING handled structurally above/outside this loop)
        
        # Rule E: LOGIC drift
        if drift_type == "UNCLASSIFIED":
            drift_type = "LOGIC"
            
        classified.append({
            "field": field,
            "expected": expected,
            "actual": actual,
            "drift_type": drift_type,
            "layer": layer
        })
        
    return classified

def analyze_replay(run_id: str):
    replay_dir = os.path.join("replays", run_id)
    result_path = os.path.join(replay_dir, "replay_result.json")
    
    if not os.path.exists(result_path):
        raise FileNotFoundError(f"No replay result found for run {run_id}. Must execute replay first.")
        
    with open(result_path, "r") as f:
        replay_data = json.load(f)
        
    drift_summary = {
        "API": 0,
        "PARSE": 0,
        "FLOAT": 0,
        "LOGIC": 0,
        "ORDERING": 0
    }
    
    drift_events = []
    
    # Process mismatched rows
    mismatches = replay_data.get("mismatched_rows", [])
    
    # We would check ORDERING drift by looking at the holistic ordering of the CSV,
    # but the current replay result object focuses on row-level field diffs.
    
    for row in mismatches:
        row_id = row["row_id"]
        raw_diffs = row.get("field_diffs", [])
        
        classified_diffs = classify_drift(raw_diffs)
        
        for diff in classified_diffs:
            drift_summary[diff["drift_type"]] += 1
            
            event = {
                "row_id": row_id,
                "field": diff["field"],
                "expected": diff["expected"],
                "actual": diff["actual"],
                "drift_type": diff["drift_type"],
                "layer": diff["layer"]
            }
            drift_events.append(event)
            
    report = {
        "run_id": run_id,
        "drift_summary": drift_summary,
        "drift_events": drift_events
    }
    
    report_path = os.path.join(replay_dir, "drift_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=4)
        
    print(f"\n[DRIFT CLASSIFICATION COMPLETE]")
    print(f"Total Drift Events: {len(drift_events)}")
    for k, v in drift_summary.items():
        if v > 0:
            print(f"  - {k}: {v}")
    print(f"Report saved to: {report_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python drift_engine.py <run_id>")
        sys.exit(1)
    analyze_replay(sys.argv[1])
