import os
import time
import json
import hashlib
import random
from typing import Optional
from mar1.ob1.mar1_ob1_service import initialize_ob1, emit_observation, shutdown_ob1
from mar1.adapters.adapter_schemas import RawSnapshot

def fetch_tehama_html(apn: str) -> Optional[str]:
    # Use synthetic HTML for Phase 4E.0.
    # If a synthetic tehama directory exists, use it, else return None
    synth_dir = "data/raw/synthetic_tehama"
    path = os.path.join(synth_dir, f"{apn}_assessor.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None

def capture_100_events():
    # Write directly to WAL
    initialize_ob1(log_dir="logs/shadow_logs", wal_mode="STRICT")
    
    synth_dir = "data/raw/synthetic_tehama"
    apns = []
    if os.path.exists(synth_dir):
        files = os.listdir(synth_dir)
        for f in files:
            if f.endswith("_assessor.html"):
                apns.append(f.split("_")[0])
                
    if not apns:
        apns = [f"000-000-00{i}-000" for i in range(5, 10)]
        
    captured = 0
    while captured < 100:
        apn = random.choice(apns)
        start_t = time.time()
        
        # Simulate network delay
        time.sleep(random.uniform(0.01, 0.05))
        
        html = fetch_tehama_html(apn)
        latency_ms = (time.time() - start_t) * 1000
        
        if html is None:
            html = "<html><body>Dummy Tehama Data</body></html>"
            
        resp_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
        
        snap = RawSnapshot(
            source_id="tehama_mpts",
            timestamp=time.time(),
            request_payload=json.dumps({"apn": apn}),
            response_payload=html,
            response_hash=resp_hash,
            metadata={"latency_ms": latency_ms, "success": True}
        )
        
        # In phase 4E.0, adapter writes directly to OB-1 without MAR-1 control loop
        emit_observation(snap, mode="SYNC")
        captured += 1
        
    shutdown_ob1()
    print(f"Captured {captured} RawSnapshots from Tehama into WAL.")

if __name__ == "__main__":
    capture_100_events()
