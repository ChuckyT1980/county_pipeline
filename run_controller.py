import uuid
import time
import sqlite3
import json
import threading
import csv
from scheduler.state_store import StateRepository
from scheduler.scheduler_main import Scheduler

def seed_queue(run_id: str, store: StateRepository) -> int:
    """Reads CSV and seeds queue_items for a new run."""
    distress_events_map = {}
    tehama_apns = []
    
    with open("tehama_tax_default_leads.csv", "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            apn = row["apn"]
            tehama_apns.append(apn)
            distress_events_map[apn] = {
                "apn": apn,
                "source": "tax_delinquency_notice",
                "amount_due": float(row["amount_due"]),
                "default_year": int(row["default_year"]),
                "notice_date": "2025-06",
                "event_type": "impending_default",
                "raw_owner_signal": row["name_address_raw"]
            }

    from scheduler.queue_manager import QueueManager
    qm = QueueManager(store)
    qm.add_work(run_id, "tehama", tehama_apns)
    return len(tehama_apns), distress_events_map

def start_controller():
    store = StateRepository()
    
    # Safety Check: Single active run lock
    with sqlite3.connect(store.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT run_id FROM runs WHERE status = 'RUNNING'")
        active_runs = cursor.fetchall()
        if active_runs:
            print(f"[CONTROLLER] REJECTED: Active run already exists ({active_runs[0][0]}).")
            return
            
    run_id = str(uuid.uuid4())
    print(f"[CONTROLLER] Starting PLS Run Context: {run_id}")
    
    # Snapshot Inputs
    total_tasks, distress_events_map = seed_queue(run_id, store)
    
    import os
    replay_dir = os.path.join("replays", run_id)
    os.makedirs(replay_dir, exist_ok=True)
    with open(os.path.join(replay_dir, "inputs.json"), "w") as f:
        json.dump(distress_events_map, f, indent=4)
        
    # Insert RUNNING state
    with sqlite3.connect(store.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO runs (run_id, status, total_tasks, last_heartbeat)
            VALUES (?, 'RUNNING', ?, CURRENT_TIMESTAMP)
        ''', (run_id, total_tasks))
        conn.commit()
        
    # Spawn Scheduler in background thread
    def run_scheduler_thread():
        scheduler = Scheduler(run_id, distress_events_map)
        scheduler.run()
        
    t = threading.Thread(target=run_scheduler_thread, daemon=True)
    t.start()
    
    # Watchdog Loop
    while True:
        time.sleep(2)
        
        with sqlite3.connect(store.db_path) as conn:
            cursor = conn.cursor()
            
            # Read-only snapshot of queue
            cursor.execute("SELECT COUNT(*) FROM queue_items WHERE run_id=? AND status='pending'", (run_id,))
            pending = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM queue_items WHERE run_id=? AND status='processing'", (run_id,))
            processing = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM queue_items WHERE run_id=? AND status='completed'", (run_id,))
            completed = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM queue_items WHERE run_id=? AND status='failed'", (run_id,))
            failed = cursor.fetchone()[0]
            
            # Read run status
            cursor.execute("SELECT status, total_tasks, last_heartbeat FROM runs WHERE run_id=?", (run_id,))
            row = cursor.fetchone()
            run_status, total_expected, last_heartbeat = row
            
            # Check Exit Conditions
            if pending == 0 and processing == 0 and run_status == "RUNNING":
                if (completed + failed) == total_expected:
                    finalize_run(run_id, store, completed, failed)
                    break
                else:
                    print(f"[CONTROLLER] WARNING: Queue drained but {completed + failed} != {total_expected}. Holding RUNNING state.")

def finalize_run(run_id: str, store: StateRepository, completed: int, failed: int):
    print(f"[CONTROLLER] Triggering FINALIZATION for {run_id}")
    
    with sqlite3.connect(store.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE runs SET status = 'FINALIZING' WHERE run_id=?", (run_id,))
        conn.commit()

    # (Flush buffers / Validate integrity would go here)
    
    # Write Final Manifest (to root and replays dir)
    manifest = {
        "run_id": run_id,
        "records_processed": completed + failed,
        "failed": failed,
        "schema_version": "v1.0",
        "status": "FINALIZED"
    }
    
    with open(f"MANIFEST_{run_id}.json", "w") as f:
        json.dump(manifest, f, indent=4)
        
    import os
    replay_dir = os.path.join("replays", run_id)
    os.makedirs(replay_dir, exist_ok=True)
    with open(os.path.join(replay_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=4)
        
    with sqlite3.connect(store.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE runs SET status = 'FINALIZED', completed_count=?, failed_count=? WHERE run_id=?", (completed, failed, run_id))
        conn.commit()
        
    print(f"[CONTROL PLANE] RUN COMPLETE")
    print(f"run_id: {run_id}")
    print(f"status: LOCKED")
    print(f"output: FINALIZED")

if __name__ == "__main__":
    start_controller()
