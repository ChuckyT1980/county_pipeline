import csv
from scheduler.scheduler_main import Scheduler

def run_pipeline():
    print("[PIPELINE FACADE] Initializing backward-compatible ingestion script...")
    
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

    # Initialize Control Plane
    scheduler = Scheduler(distress_events_map)
    
    # Check if we need to seed the queue (if it's empty)
    backlog = scheduler.queue_manager.get_backlog_size("tehama")
    if backlog == 0:
        print(f"[PIPELINE FACADE] Seeding Tehama queue with {len(tehama_apns)} APNs...")
        scheduler.queue_manager.add_work("tehama", tehama_apns)
    else:
        print(f"[PIPELINE FACADE] Found existing backlog of {backlog} APNs. Resuming...")

    # Transfer control
    scheduler.run()

if __name__ == "__main__":
    run_pipeline()
