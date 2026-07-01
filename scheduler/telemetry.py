import json
import sqlite3
from .state_store import StateRepository
from .models import CountyState

def emit_metrics(store: StateRepository, run_id: str, county: str, state: CountyState):
    metrics = {
        "drift_score": state.drift_score,
        "success_rate": state.success_rate,
        "latency": state.avg_latency_ms,
        "backlog": state.backlog_size,
    }
    
    with sqlite3.connect(store.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO telemetry (run_id, county, metrics_json)
            VALUES (?, ?, ?)
        ''', (run_id, county, json.dumps(metrics)))
        
        # Heartbeat update
        cursor.execute('''
            UPDATE runs SET last_heartbeat = CURRENT_TIMESTAMP WHERE run_id = ?
        ''', (run_id,))
        conn.commit()
    
    # Simple console output for observability during run
    print(f"[TELEMETRY] {county} | backlog: {state.backlog_size} | drift: {state.drift_score} | health: {state.success_rate:.2f}")
