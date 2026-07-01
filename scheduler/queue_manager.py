import sqlite3
from typing import List
from .models import WorkUnit
from .state_store import StateRepository

class QueueManager:
    def __init__(self, store: StateRepository):
        self.store = store

    def add_work(self, run_id: str, county: str, apns: List[str]):
        with sqlite3.connect(self.store.db_path) as conn:
            cursor = conn.cursor()
            for apn in apns:
                cursor.execute('''
                    INSERT INTO queue_items (run_id, county, apn, status)
                    VALUES (?, ?, ?, 'pending')
                ''', (run_id, county, apn))
            conn.commit()
            
    def get_next_batch(self, run_id: str, county: str, batch_size: int = 50) -> WorkUnit:
        with sqlite3.connect(self.store.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, apn FROM queue_items 
                WHERE run_id = ? AND county = ? AND status = 'pending'
                LIMIT ?
            ''', (run_id, county, batch_size))
            
            rows = cursor.fetchall()
            if not rows:
                return None
                
            apns = []
            for row in rows:
                apns.append(row[1])
                # Mark as processing (basic lock)
                cursor.execute('UPDATE queue_items SET status = "processing" WHERE id = ?', (row[0],))
                
            conn.commit()
            
            return WorkUnit(
                county=county,
                apn_batch=apns,
                endpoint="feeparcel"
            )

    def mark_completed(self, run_id: str, county: str, apns: List[str]):
        with sqlite3.connect(self.store.db_path) as conn:
            cursor = conn.cursor()
            for apn in apns:
                cursor.execute('''
                    UPDATE queue_items SET status = "completed" 
                    WHERE run_id = ? AND county = ? AND apn = ?
                ''', (run_id, county, apn))
            conn.commit()

    def get_backlog_size(self, run_id: str, county: str) -> int:
        with sqlite3.connect(self.store.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM queue_items WHERE run_id = ? AND county = ? AND status = "pending"', (run_id, county))
            return cursor.fetchone()[0]
