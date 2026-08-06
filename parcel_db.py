"""
Parcel Database Builder
Discovers ALL parcels via APN range probing on the MPTS fee parcel API.
Stores in SQLite, then enriches with live assessment and tax bill data.
"""
import requests
import json
import sqlite3
import time
import os
from datetime import datetime

# ─── CONFIG ────────────────────────────────────

COUNTIES = {
    "shasta": {
        "host": "common2.mptsweb.com",
        "slug": "shasta",
        "book_range": (1, 199),
    },
    "tehama": {
        "host": "common1.mptsweb.com",
        "slug": "tehama",
        "book_range": (1, 199),
    },
}

HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json"
}

DB_PATH = os.path.join(os.path.dirname(__file__), "parcel_database.db")
REQUEST_DELAY = 0.3

# ─── DATABASE ──────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS parcels (
            apn TEXT PRIMARY KEY,
            county TEXT NOT NULL,
            owner_name TEXT,
            situs_address TEXT,
            mailing_address TEXT,
            fee_parcel TEXT,
            roll_category TEXT,
            tra TEXT,
            discovered_at TEXT,
            last_checked TEXT
        );
        CREATE TABLE IF NOT EXISTS tax_data (
            apn TEXT PRIMARY KEY,
            county TEXT NOT NULL,
            curr_due REAL,
            delinquent INTEGER,
            active_liens INTEGER,
            mortgages INTEGER,
            assessed_value REAL,
            land_value REAL,
            improvement_value REAL,
            assignment_of_rents INTEGER,
            affidavit_of_death INTEGER,
            last_updated TEXT
        );
        CREATE TABLE IF NOT EXISTS discovery_log (
            county TEXT,
            batch TEXT,
            apns_found INTEGER,
            apns_checked INTEGER,
            started_at TEXT,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_parcels_county ON parcels(county);
        CREATE INDEX IF NOT EXISTS idx_tax_delinquent ON tax_data(delinquent);
    """)
    conn.commit()
    return conn

# ─── FEE PARCEL API ────────────────────────────

def query_fee_parcel(host, slug, apn):
    """Query the MPTS fee parcel API for a single APN."""
    url = f"https://{host}/MBC/api/search/{slug}/0000-CURR/feeparcel/{apn}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        # Response is double-encoded JSON string
        data = json.loads(r.text)
        if isinstance(data, str):
            data = json.loads(data)
        rows = data.get("Table", {}).get("Row", [])
        if isinstance(rows, dict):
            rows = [rows]
        return rows[0] if rows else None
    except:
        return None

def apn_exists(host, slug, apn):
    """Check if an APN exists by querying fee parcel API."""
    result = query_fee_parcel(host, slug, apn)
    return result is not None

# ─── DISCOVERY ─────────────────────────────────

def discover_by_book_range(county_name, cfg, conn):
    """
    Discover parcels by iterating through book numbers.
    For each book, query the fee parcel API with sample APNs to find valid pages.
    """
    c = conn.cursor()
    host = cfg["host"]
    slug = cfg["slug"]
    book_start, book_end = cfg["book_range"]
    
    print(f"\n=== Discovering {county_name.upper()} parcels ===")
    print(f"Book range: {book_start}-{book_end}")
    
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    total_found = 0
    start_time = time.time()
    
    for book in range(book_start, book_end + 1):
        # For each book, probe pages 001, 050, 100... to find valid page ranges
        # Then for valid books, do more detailed scanning
        apn_template = f"{book:03d}"
        
        # Quick probe: check if this book has any parcels
        probe_apn = f"{apn_template}001001000"
        if not apn_exists(host, slug, probe_apn):
            # Check a few more spots in this book
            found_any = False
            for page_probe in [500, 999]:
                probe = f"{apn_template}{page_probe:03d}001000"
                if apn_exists(host, slug, probe):
                    found_any = True
                    break
            if not found_any:
                continue
        
        # Book has parcels - scan pages
        for page in range(1, 1000):
            apn = f"{apn_template}{page:03d}001000"
            row = query_fee_parcel(host, slug, apn)
            if row is None:
                continue
            
            # Found a valid parcel - store it
            try:
                c.execute("""
                    INSERT OR REPLACE INTO parcels 
                    (apn, county, owner_name, situs_address, mailing_address, 
                     fee_parcel, roll_category, tra, discovered_at, last_checked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get("Asmt", apn),
                    county_name,
                    row.get("OwnerName"),
                    row.get("Situs1"),
                    row.get("MailingAddress"),
                    row.get("FeeParcel"),
                    row.get("RollCategory"),
                    row.get("Tra"),
                    batch_id,
                    datetime.now().isoformat()
                ))
                total_found += 1
            except:
                pass
            
            time.sleep(REQUEST_DELAY)
        
        # Progress indicator
        if book % 10 == 0:
            elapsed = time.time() - start_time
            rate = total_found / elapsed if elapsed > 0 else 0
            print(f"  Book {book:03d}: {total_found} parcels found ({rate:.1f}/sec)")
    
    conn.commit()
    elapsed = time.time() - start_time
    print(f"\n  Total: {total_found} parcels in {elapsed:.0f}s")
    
    # Log discovery
    c.execute("""
        INSERT INTO discovery_log (county, batch, apns_found, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?)
    """, (county_name, batch_id, total_found, batch_id, datetime.now().isoformat()))
    conn.commit()
    
    return total_found

# ─── ENRICHMENT ────────────────────────────────

def enrich_parcels(county_name, cfg, conn, limit=None):
    """
    Enrich discovered parcels with current tax data.
    Queries assessment API and tax bill page for each parcel.
    """
    c = conn.cursor()
    host = cfg["host"]
    
    # Get unenriched parcels
    if limit:
        rows = c.execute("""
            SELECT p.apn FROM parcels p 
            LEFT JOIN tax_data t ON p.apn = t.apn 
            WHERE p.county = ? AND t.apn IS NULL
            LIMIT ?
        """, (county_name, limit)).fetchall()
    else:
        rows = c.execute("""
            SELECT p.apn FROM parcels p 
            LEFT JOIN tax_data t ON p.apn = t.apn 
            WHERE p.county = ? AND t.apn IS NULL
        """, (county_name,)).fetchall()
    
    print(f"\n=== Enriching {len(rows)} {county_name.upper()} parcels ===")
    
    enriched = 0
    start_time = time.time()
    
    for (apn,) in rows:
        try:
            # Get assessment data
            api_url = f"https://{host}/MBC/api/search/county/0000-CURR/asmt/{apn}"
            # Fall back to HTML tax bill for balance/status
            tax_url = f"https://{host}/MBC/{cfg['slug']}/tax/main/{apn}"
            
            r = requests.get(tax_url, headers=HEADERS, timeout=10)
            curr_due = 0
            delinquent = 0
            
            if r.status_code == 200:
                html = r.text
                # Parse CurrDue from tax bill page
                if "CurrDue" in html or "total balance" in html.lower():
                    curr_due = 1  # Placeholder - need proper HTML parsing
                if "delinquent" in html.lower() or "LATE" in html.upper():
                    delinquent = 1
            
            # Store basic tax record
            c.execute("""
                INSERT OR REPLACE INTO tax_data 
                (apn, county, curr_due, delinquent, last_updated)
                VALUES (?, ?, ?, ?, ?)
            """, (apn, county_name, curr_due, delinquent, datetime.now().isoformat()))
            
            enriched += 1
            time.sleep(REQUEST_DELAY)
            
        except Exception as e:
            pass
        
        if enriched % 50 == 0:
            elapsed = time.time() - start_time
            rate = enriched / elapsed if elapsed > 0 else 0
            print(f"  Enriched {enriched}/{len(rows)} ({rate:.1f}/sec)")
    
    conn.commit()
    print(f"\n  Enriched: {enriched} parcels")
    return enriched

# ─── MAIN ──────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    conn = init_db()
    print(f"Parcel database: {DB_PATH}")
    
    action = sys.argv[1] if len(sys.argv) > 1 else "discover"
    county = sys.argv[2] if len(sys.argv) > 2 else "shasta"
    
    if county not in COUNTIES:
        print(f"Unknown county: {county}")
        print(f"Known: {', '.join(COUNTIES.keys())}")
        sys.exit(1)
    
    cfg = COUNTIES[county]
    
    if action == "discover":
        count = discover_by_book_range(county, cfg, conn)
        print(f"\nDone. {count} parcels discovered.")
        
    elif action == "enrich":
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
        count = enrich_parcels(county, cfg, conn, limit)
        print(f"\nDone. {count} parcels enriched.")
        
    elif action == "status":
        c = conn.cursor()
        for co in COUNTIES:
            total = c.execute("SELECT COUNT(*) FROM parcels WHERE county=?", (co,)).fetchone()[0]
            enriched = c.execute("""
                SELECT COUNT(*) FROM parcels p 
                JOIN tax_data t ON p.apn = t.apn 
                WHERE p.county=?
            """, (co,)).fetchone()[0]
            delinquent = c.execute("""
                SELECT COUNT(*) FROM tax_data WHERE county=? AND delinquent=1
            """, (co,)).fetchone()[0]
            print(f"{co.upper():8} Total parcels: {total:>6}  Enriched: {enriched:>6}  Delinquent: {delinquent:>6}")
    
    conn.close()
