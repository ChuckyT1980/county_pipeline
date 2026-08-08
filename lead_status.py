"""
Lead status state machine for excess-proceeds / surplus records.

Built directly from the Nevada incident (2026-08-08): a real document
was extracted and source-verified, but its deadline had already passed
— and without an explicit, enforced state machine, a record like that
could silently end up presented as active. This module makes that
impossible by construction: ACTIVE_CANDIDATE is only reachable through
a real, parsed, future-dated deadline. There is no path around it.

State flow:

    EXTRACTED
        -> SOURCE_VERIFIED       (source URL fetched, artifact hashed)
            -> DEADLINE_VERIFIED  (a deadline string was found AND
                                    successfully parsed as a real date)
                -> EXPIRED                    (parsed deadline <= run_date)
                -> CLAIMABILITY_UNCONFIRMED    (future deadline, amount
                                                 not disclosed by county)
                -> CLAIMABILITY_POSSIBLE       (future deadline, amount
                                                 disclosed by county)
                    -> ACTIVE_CANDIDATE         (only reachable from
                                                   CLAIMABILITY_UNCONFIRMED
                                                   or CLAIMABILITY_POSSIBLE)
            -> DEADLINE_UNVERIFIABLE   (deadline missing or unparseable -
                                         dead end, requires human review,
                                         NEVER reaches ACTIVE_CANDIDATE)

HARD RULE (this is the whole point of this module): a record cannot
become ACTIVE_CANDIDATE unless a deadline was actually extracted,
parsed into a real date, and confirmed later than the run date. There
is no code path that skips this check. If you're tempted to add one,
don't — that's exactly the bug this module exists to prevent.
"""
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class LeadStatus(str, Enum):
    EXTRACTED = "extracted"
    SOURCE_VERIFIED = "source_verified"
    DEADLINE_VERIFIED = "deadline_verified"
    DEADLINE_UNVERIFIABLE = "deadline_unverifiable"
    EXPIRED = "expired"
    CLAIMABILITY_UNCONFIRMED = "claimability_unconfirmed"
    CLAIMABILITY_POSSIBLE = "claimability_possible"
    ACTIVE_CANDIDATE = "active_candidate"


@dataclass
class LeadEvaluation:
    status: LeadStatus
    reason: str
    deadline_parsed: date | None = None
    days_remaining: int | None = None
    history: list[LeadStatus] = field(default_factory=list)


def evaluate_lead(
    *,
    source_verified: bool,
    deadline_raw: str | None,
    run_date: date,
    amount_disclosed: bool,
) -> LeadEvaluation:
    """
    Evaluate a single extracted record through the state machine.
    Never returns ACTIVE_CANDIDATE unless deadline_raw parses to a real
    date that is strictly after run_date.
    """
    history = [LeadStatus.EXTRACTED]

    if not source_verified:
        return LeadEvaluation(
            status=LeadStatus.EXTRACTED,
            reason="Source not yet verified (no fetched/hashed artifact) - cannot proceed",
            history=history,
        )
    history.append(LeadStatus.SOURCE_VERIFIED)

    if not deadline_raw:
        history.append(LeadStatus.DEADLINE_UNVERIFIABLE)
        return LeadEvaluation(
            status=LeadStatus.DEADLINE_UNVERIFIABLE,
            reason="No deadline string found in the source - requires human review, cannot become active",
            history=history,
        )

    parsed = _try_parse_date(deadline_raw)
    if parsed is None:
        history.append(LeadStatus.DEADLINE_UNVERIFIABLE)
        return LeadEvaluation(
            status=LeadStatus.DEADLINE_UNVERIFIABLE,
            reason=f"Deadline string '{deadline_raw}' found but could not be parsed as a date - requires human review",
            history=history,
        )

    history.append(LeadStatus.DEADLINE_VERIFIED)
    days_remaining = (parsed - run_date).days

    if parsed <= run_date:
        history.append(LeadStatus.EXPIRED)
        return LeadEvaluation(
            status=LeadStatus.EXPIRED,
            reason=f"Deadline {parsed.isoformat()} is on or before run date {run_date.isoformat()} "
                   f"({abs(days_remaining)} days ago) - EXCLUDED from active inventory, never claimable",
            deadline_parsed=parsed,
            days_remaining=days_remaining,
            history=history,
        )

    pre_active = LeadStatus.CLAIMABILITY_POSSIBLE if amount_disclosed else LeadStatus.CLAIMABILITY_UNCONFIRMED
    history.append(pre_active)
    history.append(LeadStatus.ACTIVE_CANDIDATE)
    return LeadEvaluation(
        status=LeadStatus.ACTIVE_CANDIDATE,
        reason=f"Deadline {parsed.isoformat()} is {days_remaining} days in the future as of {run_date.isoformat()} "
               f"- amount {'disclosed' if amount_disclosed else 'not disclosed'} by county",
        deadline_parsed=parsed,
        days_remaining=days_remaining,
        history=history,
    )


_MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def _try_parse_date(raw: str) -> date | None:
    """Parse 'November 27, 2025' or '2025-11-27' - returns None, never guesses, on failure."""
    raw = raw.strip()
    # ISO format
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass
    # 'Month DD, YYYY'
    import re
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        month_name, day, year = m.groups()
        month = _MONTHS.get(month_name.upper())
        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                return None
    return None
