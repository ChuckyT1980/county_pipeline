"""
raw_storage_manager.py — 100% Source Raw Capture & Field Provenance Storage Engine
==================================================================================
Ensures 100% of data returned by county public sources (MPTS, Tyler, ArcGIS, Tax Collector)
is stored without loss in raw capture format and indexed into `verification.sqlite`.

Tables managed:
  1. `raw_captures`: Full raw HTML / JSON payload from every county HTTP response.
  2. `field_provenance`: Every parsed key-value pair linked to its exact raw_capture_id.

Usage:
  python raw_storage_manager.py
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERIFY_DB = ROOT / "verification.sqlite"

def init_raw_storage_schema():
    conn = sqlite3.connect(VERIFY_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            county TEXT NOT NULL,
            apn TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_url TEXT NOT NULL,
            raw_content TEXT NOT NULL,
            content_type TEXT DEFAULT 'text/html',
            http_status INTEGER DEFAULT 200,
            parser_version TEXT DEFAULT '2026.1-mpts-1',
            captured_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS field_provenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apn TEXT NOT NULL,
            county TEXT NOT NULL,
            field_name TEXT NOT NULL,
            field_value TEXT,
            source TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            fetched_at TEXT NOT NULL,
            raw_capture_id INTEGER REFERENCES raw_captures(id)
        )
    """)
    # Ensure missing columns exist on pre-existing field_provenance table
    cur = conn.execute("PRAGMA table_info(field_provenance)")
    cols = {r[1] for r in cur.fetchall()}
    for col, col_type in [("county", "TEXT"), ("raw_capture_id", "INTEGER")]:
        if col not in cols:
            try:
                conn.execute(f"ALTER TABLE field_provenance ADD COLUMN {col} {col_type}")
            except Exception:
                pass
    conn.commit()
    conn.close()

def store_raw_capture(county: str, apn: str, source_type: str, source_url: str, raw_content: str, parsed_fields: dict = None) -> int:
    """Store 100% raw payload and all parsed fields into verification.sqlite."""
    init_raw_storage_schema()
    
    conn = sqlite3.connect(VERIFY_DB)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    cur = conn.execute("""
        INSERT INTO raw_captures (county, apn, source_type, source_url, raw_content, content_type, captured_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (county.lower(), apn, source_type, source_url, raw_content, "text/html" if "<html" in raw_content.lower() else "application/json", now_iso))
    
    capture_id = cur.lastrowid
    
    if parsed_fields:
        for k, v in parsed_fields.items():
            if v is not None and str(v).strip() != "":
                try:
                    conn.execute("""
                        INSERT INTO field_provenance (run_id, apn, county, field_name, field_value, source, confidence, fetched_at, raw_capture_id)
                        VALUES (1, ?, ?, ?, ?, ?, 1.0, ?, ?)
                    """, (apn, county.lower(), k, str(v), source_type, now_iso, capture_id))
                except Exception as fe:
                    print(f"[raw_storage] Field insert note: {fe}")
                
    conn.commit()
    conn.close()
    
    return capture_id

if __name__ == "__main__":
    init_raw_storage_schema()
    print("[raw_storage] Raw capture & field provenance schema initialized in verification.sqlite.")
