import os
import json
import sqlite3
from typing import Dict, Any
from connectors.base import RawPayload

class DependencyFreeze:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.replay_dir = os.path.join("replays", run_id)
        os.makedirs(self.replay_dir, exist_ok=True)
        self.db_path = os.path.join(self.replay_dir, "dependency_freeze.sqlite")
        self.state_db = "scheduler_v2.db"
        self._init_db()

    def _is_finalized(self) -> bool:
        if not os.path.exists(self.state_db):
            return False
        with sqlite3.connect(self.state_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM runs WHERE run_id = ?", (self.run_id,))
            row = cursor.fetchone()
            if row and row[0] == "FINALIZED":
                return True
        return False

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_cache (
                    apn TEXT,
                    endpoint TEXT,
                    payload_json TEXT,
                    PRIMARY KEY (apn, endpoint)
                )
            ''')
            conn.commit()

    def record(self, apn: str, endpoint: str, payload: RawPayload):
        if self._is_finalized():
            raise RuntimeError(f"[IMMUTABILITY VIOLATION] Run {self.run_id} is FINALIZED. DependencyFreeze is strictly read-only.")
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO api_cache (apn, endpoint, payload_json)
                VALUES (?, ?, ?)
            ''', (apn, endpoint, json.dumps(payload.__dict__)))
            conn.commit()

    def retrieve(self, apn: str, endpoint: str) -> RawPayload:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT payload_json FROM api_cache WHERE apn = ? AND endpoint = ?
            ''', (apn, endpoint))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"[REPLAY ERROR] Determinism violation! Missing freeze data for {apn} at {endpoint}")
            data = json.loads(row[0])
            return RawPayload(**data)
