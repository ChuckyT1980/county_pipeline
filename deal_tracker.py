import json
from datetime import datetime

def log_deal_event(record):
    """
    Logs deal progress events to the tracking file for CPS-1 learning.
    
    Expected schema:
    {
      "apn": "054-090-012-000",
      "county": "Tehama",
      "buyer_contacted": True,
      "response_type": "interested",
      "stage": "follow_up",
      "deal_status": "pending",
      "expected_profit": 25000,
      "closed": False
    }
    """
    record["timestamp"] = str(datetime.utcnow())
    
    with open("deal_tracker.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
        
    print(f"[CPS-1 TRACKER] Logged deal event for APN {record.get('apn')} | Stage: {record.get('stage')}")

if __name__ == "__main__":
    # Test example to ensure tracker loop works
    sample_event = {
      "apn": "049-040-021-000",
      "county": "Tehama",
      "buyer_contacted": True,
      "response_type": "high_interest",
      "stage": "offer_made",
      "deal_status": "negotiating",
      "expected_profit": 15000,
      "closed": False
    }
    log_deal_event(sample_event)
