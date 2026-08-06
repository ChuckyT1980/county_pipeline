"""
Automated County Auction Date Tracker / Monitor
Scrapes county tax collector portals and auction platform listings.
Updates: data/auction_calendar.csv
Logs changes: monitor/monitor_log.csv
"""
import os
import re
import sys
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

MONITOR_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(MONITOR_DIR)
CALENDAR_CSV = os.path.join(PIPELINE_DIR, "data", "auction_calendar.csv")
LOG_CSV = os.path.join(MONITOR_DIR, "monitor_log.csv")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def log_change(county, year, platform, field_changed, old_val, new_val, notes=""):
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_entry = {
        "date_detected": today_str,
        "county": county,
        "year": year,
        "platform": platform,
        "field_changed": field_changed,
        "old_value": old_val,
        "new_value": new_val,
        "notes": notes
    }
    
    if os.path.exists(LOG_CSV):
        df_log = pd.read_csv(LOG_CSV)
        df_log = pd.concat([df_log, pd.DataFrame([log_entry])], ignore_index=True)
    else:
        df_log = pd.DataFrame([log_entry])
        
    df_log.to_csv(LOG_CSV, index=False)
    print(f"  [ALERT] Logged change for {county} {year} ({field_changed}: {old_val} -> {new_val})")

def check_county_site(url):
    """Attempt HTTP request to verify if site is responsive and parse text."""
    if not url or str(url).strip() == "" or "http" not in str(url):
        return None, "No URL provided"
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text()
            return text, "OK"
        else:
            return None, f"HTTP {resp.status_code}"
    except Exception as e:
        return None, f"Error: {str(e)[:40]}"

def run_monitor():
    print(f"=== Running County Auction Date Monitor [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===")
    if not os.path.exists(CALENDAR_CSV):
        print(f"ERROR: Calendar CSV not found at {CALENDAR_CSV}")
        return

    df = pd.read_csv(CALENDAR_CSV, dtype=str)
    today_str = datetime.now().strftime("%Y-%m-%d")
    changes_count = 0

    print(f"Loaded {len(df)} county auction records from calendar.")

    for idx, row in df.iterrows():
        county = row["county"]
        year = row["year"]
        platform = row["platform"]
        url = row["url"]
        status = row.get("status", "UPCOMING")

        print(f"\nChecking [{idx+1}/{len(df)}] {county} County ({year} - {platform})...")
        
        # Verify URL availability
        text, msg = check_county_site(url)
        print(f"  URL ({url}): {msg}")

        # Update last_verified date
        df.at[idx, "last_verified"] = today_str

        # Basic check for date status changes
        if text:
            # Check for words like "cancelled", "postponed", "concluded"
            lower_text = text.lower()
            if "cancelled" in lower_text or "canceled" in lower_text:
                if "CANCELLED" not in str(status).upper():
                    log_change(county, year, platform, "status", status, "CANCELLED", "Detected cancellation keyword on site")
                    df.at[idx, "status"] = "CANCELLED"
                    changes_count += 1
            elif "postponed" in lower_text:
                if "POSTPONED" not in str(status).upper():
                    log_change(county, year, platform, "status", status, "POSTPONED", "Detected postponement keyword on site")
                    df.at[idx, "status"] = "POSTPONED"
                    changes_count += 1

    # Save updated calendar back
    df.to_csv(CALENDAR_CSV, index=False)
    print(f"\n============================================================")
    print(f"Monitor run complete. {changes_count} changes detected.")
    print(f"Calendar saved: {CALENDAR_CSV} (all records stamped as verified {today_str})")

if __name__ == "__main__":
    run_monitor()
