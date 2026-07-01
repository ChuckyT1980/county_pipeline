import time
from .state_store import StateRepository
from .county_registry import load_counties
from .queue_manager import QueueManager
from .rate_limiter import compute_throttle
from .dispatcher import dispatch_batch
from .telemetry import emit_metrics

class Scheduler:
    def __init__(self, run_id: str, distress_events_map: dict = None):
        self.run_id = run_id
        self.store = StateRepository()
        self.queue_manager = QueueManager(self.store)
        self.distress_events_map = distress_events_map or {}
        
    def run(self):
        print("[CONTROL PLANE] Starting Multi-County Execution Scheduler...")
        
        while True:
            # Refresh state from DB
            counties = load_counties(self.store)
            active_work = False
            
            for county_name, state in counties.items():
                # 1. Update backlog size
                state.backlog_size = self.queue_manager.get_backlog_size(self.run_id, county_name)
                if state.backlog_size == 0:
                    continue
                    
                active_work = True

                # 2. Compute adaptive throttle
                throttle = compute_throttle(state)
                if throttle.blocked:
                    print(f"[THROTTLE] {county_name} is blocked (high drift or low reliability). Backing off.")
                    continue

                # 3. Fetch next work unit
                work_unit = self.queue_manager.get_next_batch(self.run_id, county_name, batch_size=10)
                if not work_unit:
                    continue

                # 4. Dispatch work
                success_count, success_rate, avg_latency = dispatch_batch(
                    self.run_id,
                    work_unit, 
                    rps=throttle.rps,
                    distress_events_map=self.distress_events_map
                )

                # 5. Update state feedback
                # Moving average for latency and success rate (simple dampening)
                state.success_rate = (state.success_rate * 0.7) + (success_rate * 0.3)
                state.avg_latency_ms = (state.avg_latency_ms * 0.7) + (avg_latency * 0.3)
                self.store.save_state(state)
                
                # Mark queue items completed if successful
                if success_rate == 1.0:
                    self.queue_manager.mark_completed(self.run_id, county_name, work_unit.apn_batch)

                # 6. Telemetry
                emit_metrics(self.store, self.run_id, county_name, state)

            if not active_work:
                print(f"[CONTROL PLANE] Scheduler drained for run {self.run_id}. Exiting loop.")
                break
            else:
                time.sleep(0.5)
