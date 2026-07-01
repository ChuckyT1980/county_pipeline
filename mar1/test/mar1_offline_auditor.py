import os
import json
import hashlib
from mar1.adapters.adapter_schemas import RawSnapshot

def verify_replay_equivalence(log_dir="logs/shadow_logs"):
    if not os.path.exists(log_dir):
        print(f"Log directory {log_dir} not found.")
        return
        
    files = [f for f in os.listdir(log_dir) if f.endswith('.jsonl')]
    if not files:
        print("No WAL files found!")
        return
        
    total_events = 0
    replay_failures = 0
    
    for f_name in files:
        with open(os.path.join(log_dir, f_name), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                
                total_events += 1
                
                # 1. Parse into Object
                data = json.loads(line)
                
                if data.get('type') == 'RawSnapshot':
                    snap = RawSnapshot(
                        source_id=data['source_id'],
                        timestamp=data['timestamp'],
                        request_payload=data['request_payload'],
                        response_payload=data['response_payload'],
                        response_hash=data['response_hash'],
                        metadata=data['metadata']
                    )
                    
                    # 2. Serialize again
                    replayed_str = snap.to_json()
                    
                    # 3. Hash equivalence
                    live_hash = hashlib.sha256(line.encode('utf-8')).hexdigest()
                    replay_hash = hashlib.sha256(replayed_str.encode('utf-8')).hexdigest()
                    
                    if live_hash != replay_hash:
                        replay_failures += 1
                else:
                    print(f"Unknown event type in WAL: {data.get('type')}")
                    replay_failures += 1
                
    print(f"=== REPLAY EQUIVALENCE CERTIFICATION ===")
    print(f"Total Captured Events: {total_events}")
    print(f"Replay Failures:       {replay_failures}")
    if replay_failures == 0 and total_events >= 200:
        print("STATUS: PASS (100% Hash Consistency)")
    else:
        print("STATUS: FAIL")

if __name__ == "__main__":
    verify_replay_equivalence()
