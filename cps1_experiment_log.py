import json
from datetime import datetime

def log_experiment(record):
    """
    Logs the outcome of the 5-buyer A/B/C outreach experiment.
    
    EXPECTED STRUCTURE:
    {
      "buyer_group": "A | B | C",
      "county": "Tehama",
      "apn_sampled": True,
      "response": "positive | neutral | negative",
      "response_type": "interest | price_request | ignore | confusion",
      "subject_line_variant": "raw | ranked | system",
      "time_to_response_minutes": 0,
      "asked_for_more": True,
      "requested_dashboard": False
    }
    """
    record["timestamp"] = str(datetime.utcnow())
    with open("cps1_experiment_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
        
    print(f"[CPS-1 EXPERIMENT] Logged interaction for Group {record.get('buyer_group')}")

if __name__ == "__main__":
    # Test example
    sample = {
      "buyer_group": "B",
      "county": "Tehama",
      "apn_sampled": True,
      "response": "positive",
      "response_type": "price_request",
      "subject_line_variant": "ranked",
      "time_to_response_minutes": 15,
      "asked_for_more": True,
      "requested_dashboard": False
    }
    log_experiment(sample)
