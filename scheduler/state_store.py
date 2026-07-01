import sqlite3
import json
from .models import CountyState

class StateRepository:
    def __init__(self, db_path="scheduler_v2.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Runs tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_heartbeat TIMESTAMP,
                    completed_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    total_tasks INTEGER DEFAULT 0
                )
            ''')
            
            # County states (global rate limits across runs)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS county_state (
                    county TEXT PRIMARY KEY,
                    max_rps REAL,
                    drift_score REAL,
                    success_rate REAL,
                    avg_latency_ms REAL,
                    backlog_size INTEGER
                )
            ''')
            
            # Work Queue
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS queue_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    county TEXT,
                    apn TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Telemetry metrics
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    county TEXT,
                    metrics_json TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def save_state(self, state: CountyState):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO county_state 
                (county, max_rps, drift_score, success_rate, avg_latency_ms, backlog_size)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                state.county, 
                state.max_rps, 
                state.drift_score, 
                state.success_rate, 
                state.avg_latency_ms, 
                state.backlog_size
            ))
            conn.commit()

    def load_state(self, county: str) -> CountyState:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM county_state WHERE county = ?', (county,))
            row = cursor.fetchone()
            
            if row:
                return CountyState(
                    county=row[0],
                    max_rps=row[1],
                    drift_score=row[2],
                    success_rate=row[3],
                    avg_latency_ms=row[4],
                    backlog_size=row[5]
                )
            return None
