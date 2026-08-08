"""
Two-sided signal priority logic.

Per the business model: for a county with an imminent/current auction, the
#1 signal is "this parcel is genuinely still headed to auction" (pre-auction
intel product). Once a county's auction has already happened, the relevant
signal shifts to excess-proceeds/former-owner recovery, since CA law gives
roughly a year after the sale to claim surplus funds (R&T Code 4675 —
"parties of interest" have until 1 year after the auction's Notice of
Excess Proceeds recordation, in practice tracked from the sale date).

Auction dates below are sourced from real, verified material found for each
county tonight (2026-08-06) — not guessed:
  - Butte:  Aug 7-10, 2026  (Bid4Assets re-offer, 104 parcels)
  - Fresno: Sep 10-11, 2026 (Board of Supervisors Resolution 26-245)
  - Kern:   Sep 14-16, 2026 (county-confirmed via assessor site correspondence)
  - Tehama: no scheduled auction ("tentatively planning first half of 2027")
"""
from __future__ import annotations

from datetime import date, timedelta

AUCTION_CALENDAR = {
    "butte":  {"start": date(2026, 8, 7),  "end": date(2026, 8, 10)},
    "fresno": {"start": date(2026, 9, 10), "end": date(2026, 9, 11)},
    "kern":   {"start": date(2026, 9, 14), "end": date(2026, 9, 16)},
    "tehama": None,
}

EXCESS_PROCEEDS_CLAIM_WINDOW_DAYS = 365  # approximate — real deadline is parcel-specific


def get_auction_window_display(county_key: str) -> str:
    """Real auction window string for a county, or an honest 'not yet scheduled'."""
    cal = AUCTION_CALENDAR.get(county_key.lower())
    if not cal:
        return "Not yet scheduled"
    return f"{cal['start'].isoformat()} to {cal['end'].isoformat()}"


def get_signal(county_key: str, today: date | None = None) -> dict:
    """Return the priority signal for a county as of `today` (defaults to real today)."""
    today = today or date.today()
    cal = AUCTION_CALENDAR.get(county_key.lower())

    if not cal:
        return {
            "signal_type": "NO_SCHEDULED_AUCTION",
            "priority_label": "No scheduled auction — monitor for a future sale date",
            "days_until_auction": None,
            "days_since_auction": None,
            "claim_deadline": None,
        }

    if today < cal["start"]:
        days = (cal["start"] - today).days
        return {
            "signal_type": "PRE_AUCTION_PRIORITY_1",
            "priority_label": f"GOING TO AUCTION in {days} day{'s' if days != 1 else ''} "
                               f"({cal['start'].isoformat()} - {cal['end'].isoformat()})",
            "days_until_auction": days,
            "days_since_auction": None,
            "claim_deadline": None,
        }

    if cal["start"] <= today <= cal["end"]:
        return {
            "signal_type": "AUCTION_LIVE",
            "priority_label": f"AUCTION LIVE NOW (through {cal['end'].isoformat()})",
            "days_until_auction": 0,
            "days_since_auction": 0,
            "claim_deadline": None,
        }

    days_since = (today - cal["end"]).days
    claim_deadline = cal["end"] + timedelta(days=EXCESS_PROCEEDS_CLAIM_WINDOW_DAYS)
    return {
        "signal_type": "EXCESS_PROCEEDS_WINDOW",
        "priority_label": f"Auction complete ({days_since} days ago) — excess proceeds claim "
                           f"window open, approx. deadline {claim_deadline.isoformat()}",
        "days_until_auction": None,
        "days_since_auction": days_since,
        "claim_deadline": claim_deadline.isoformat(),
    }
