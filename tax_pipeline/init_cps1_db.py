import sqlite3
import os

DB_PATH = "tax_pipeline/cps1_outcomes.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table 1: Leads Snapshot
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            lead_id TEXT PRIMARY KEY,
            county TEXT,
            apn TEXT,
            owner_name TEXT,
            address TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Table 2: Score Snapshots (history of scoring)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS score_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT,
            score INTEGER,
            score_reason TEXT,
            calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
        )
    ''')
    
    # Table 3: Outcome Events (log of outreach)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outcome_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT,
            snapshot_id INTEGER,
            event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            outcome_tag TEXT,
            wholesaler_name TEXT,
            notes TEXT,
            FOREIGN KEY (lead_id) REFERENCES leads(lead_id),
            FOREIGN KEY (snapshot_id) REFERENCES score_snapshots(snapshot_id)
        )
    ''')
    
    # Table 4: Verification Events (log of manual human verification)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verification_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT,
            snapshot_id INTEGER,
            event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            verification_status TEXT,
            wholesaler_name TEXT,
            notes TEXT,
            FOREIGN KEY (lead_id) REFERENCES leads(lead_id),
            FOREIGN KEY (snapshot_id) REFERENCES score_snapshots(snapshot_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Successfully initialized CPS-1 database at {DB_PATH}")

if __name__ == "__main__":
    init_db()
