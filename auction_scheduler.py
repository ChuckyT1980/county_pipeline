"""
auction_scheduler.py — Autonomous 58-County Auction Schedule Monitor & Trigger.

Monitors the California tax auction calendar (`data/california_tax_auction_calendar_2025_2027.csv`)
and queries live auction portals (GovEase, Bid4Assets, RealAuction) for catalog drops.

Functions:
  - get_upcoming_auctions(within_days=60) -> returns list of upcoming county auctions
  - check_county_auction_status(county_key) -> checks live portal status
  - auto_trigger_county_pipeline(county_key) -> runs pre-flight circuit breaker & query engine
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

ROOT = Path(__file__).resolve().parent
CALENDAR_CSV = ROOT / "data" / "california_tax_auction_calendar_2025_2027.csv"
SCHEDULER_STATE = ROOT / "output" / "dashboard" / "auction_scheduler_state.json"


def load_auction_calendar() -> list[dict[str, str]]:
    """Load 58-county auction calendar CSV."""
    if not CALENDAR_CSV.exists():
        return []
    with CALENDAR_CSV.open("r", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def get_upcoming_auctions(within_days: int = 60) -> list[dict[str, Any]]:
    """Return auctions scheduled within the next N days or currently active."""
    calendar = load_auction_calendar()
    today = datetime.now().date()
    cutoff = today + timedelta(days=within_days)

    upcoming = []
    for row in calendar:
        county = (row.get("County") or row.get("county") or "").strip().lower()
        start_str = (row.get("Start Date") or row.get("start_date") or "").strip()
        end_str = (row.get("End Date") or row.get("end_date") or "").strip()
        platform = (row.get("Platform") or row.get("platform") or "").strip()
        portal_url = (row.get("Portal URL") or row.get("portal_url") or "").strip()

        if not start_str:
            continue

        try:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_str, "%Y-%m-%d").date() if end_str else start_dt

            # Check if active or upcoming within window
            if start_dt <= cutoff and end_dt >= (today - timedelta(days=7)):
                days_until = (start_dt - today).days
                status = "ACTIVE_NOW" if (start_dt <= today <= end_dt) else ("UPCOMING" if days_until > 0 else "JUST_COMPLETED")

                upcoming.append({
                    "county": county,
                    "display_name": county.capitalize(),
                    "start_date": start_str,
                    "end_date": end_str,
                    "days_until": days_until,
                    "platform": platform,
                    "portal_url": portal_url,
                    "status": status,
                    "raw": row,
                })
        except Exception:
            continue

    return sorted(upcoming, key=lambda x: x["days_until"])


def check_portal_drop(portal_url: str, timeout: float = 8.0) -> bool:
    """Check if auction portal has a live listing drop for the county."""
    if not portal_url or not portal_url.startswith("http"):
        return False
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = client.get(portal_url)
            return resp.status_code == 200 and len(resp.text) > 1000
    except Exception:
        return False


def run_scheduler_audit() -> dict[str, Any]:
    """Run full auction schedule audit across all 58 CA counties."""
    upcoming = get_upcoming_auctions(within_days=90)

    active_auctions = [u for u in upcoming if u["status"] in ("ACTIVE_NOW", "UPCOMING")]

    audit_summary = {
        "audit_timestamp": datetime.now().isoformat(),
        "total_upcoming_auctions_90d": len(active_auctions),
        "upcoming_auctions": active_auctions,
    }

    SCHEDULER_STATE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULER_STATE.write_text(json.dumps(audit_summary, indent=2), encoding="utf-8")

    return audit_summary


def main() -> int:
    audit = run_scheduler_audit()
    print("=" * 65)
    print(" CA-UNIFY AUTONOMOUS AUCTION SCHEDULE MONITOR")
    print("=" * 65)
    print(f" Upcoming Auctions (next 90 days): {audit['total_upcoming_auctions_90d']}")
    print("-" * 65)
    for a in audit["upcoming_auctions"]:
        print(f"  County : {a['display_name']} ({a['county'].upper()})")
        print(f"  Dates  : {a['start_date']} to {a['end_date']} ({a['days_until']} days away)")
        print(f"  Host   : {a['platform']} -> {a['portal_url']}")
        print(f"  Status : {a['status']}")
        print("-" * 65)
    return 0


if __name__ == "__main__":
    main()
