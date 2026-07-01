import time
import json
import uuid
import queue
import threading
import os

class RawSnapshot:
    @staticmethod
    def freeze(endpoint: str, payload: str, timestamp: float) -> dict:
        return {
            "event_id": str(uuid.uuid4()),
            "timestamp": timestamp,
            "endpoint": endpoint,
            "payload_raw": payload
        }

class KillFlag:
    def __init__(self):
        self.value = True

def wal_writer_thread(wal_queue, kill_flag, wal_path="canary_wal.jsonl"):
    with open(wal_path, "a", encoding="utf-8") as f:
        while kill_flag.value or not wal_queue.empty():
            try:
                event = wal_queue.get(timeout=0.1)
                f.write(json.dumps(event) + "\n")
                f.flush()
                os.fsync(f.fileno()) # Strict write-to-disk-before-process
                wal_queue.task_done()
            except queue.Empty:
                continue

class CanaryIngress:
    def __init__(self, endpoints, wal_queue, kill_flag):
        self.endpoints = endpoints
        self.wal_queue = wal_queue
        self.kill_flag = kill_flag

    def _fetch(self, ep: str) -> str:
        # Simulated external fetch without retry or adaptive timeout.
        # In actual production, this is a strict requests.get(ep, timeout=5.0).text
        # We simulate this by reading a single line from our synthetic corpus.
        time.sleep(0.01) # Simulate network latency
        return json.dumps({"source": ep, "data": "simulated_response", "status": "200"})

    def run(self):
        for ep in self.endpoints:
            if not self.kill_flag.value:
                break
            
            try:
                raw = self._fetch(ep)
            except Exception as e:
                # Failure treated as data
                raw = f"FAILURE: {str(e)}"

            event = RawSnapshot.freeze(
                endpoint=ep,
                payload=raw,
                timestamp=time.time()
            )

            self.wal_queue.put_nowait(event)

def run_canary_node(endpoints):
    print("[CDS-1] Starting Canary Ingress Node...")
    wal_queue = queue.Queue()
    kill_flag = KillFlag()

    writer = threading.Thread(target=wal_writer_thread, args=(wal_queue, kill_flag))
    writer.start()

    ingress = CanaryIngress(endpoints, wal_queue, kill_flag)
    
    # Run the ingress loop
    ingress.run()
    
    print("[CDS-1] Ingress complete. Draining WAL...")
    # Clean shutdown via Kill Switch
    kill_flag.value = False
    writer.join()
    print("[CDS-1] WAL synced and process terminated cleanly.")
