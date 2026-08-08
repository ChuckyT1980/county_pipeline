"""
Phase 1 lifecycle validation for property_intelligence_v2.

Scope, deliberately kept narrow: this module answers "is this status
transition structurally valid?" for the four entities that carry a
lifecycle status (IngestionRun, ParcelMatch, CanonicalPropertyState,
Exception_). It does NOT decide what SHOULD happen given a particular
failure (that would be scoring/routing/decision logic, out of scope for
"Phase 1 data-contract foundation" per the explicit instruction not to
build scoring models, ranking, or business logic yet) - it only enforces
that a proposed transition is one this system recognizes as legitimate.

This is the direct implementation of rule 1 from contracts/entities.py:
a failure is a valid output. Every transition table below includes
explicit failure/terminal states (FAILED, REJECTED, QUARANTINED,
CONTESTED, ...) as first-class destinations, not just success paths.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "contracts"))

from entities import (  # noqa: E402
    CanonicalStateLifecycle,
    ExceptionStatus,
    IngestionRunStatus,
    MatchStatus,
)


class InvalidTransitionError(ValueError):
    pass


# ── IngestionRun ─────────────────────────────────────────────────────────
# attempt -> observe -> classify -> save evidence -> record outcome
_INGESTION_RUN_TRANSITIONS: dict[IngestionRunStatus, set[IngestionRunStatus]] = {
    IngestionRunStatus.ATTEMPTED: {IngestionRunStatus.IN_PROGRESS, IngestionRunStatus.FAILED},
    IngestionRunStatus.IN_PROGRESS: {
        IngestionRunStatus.SUCCEEDED,
        IngestionRunStatus.PARTIAL,
        IngestionRunStatus.FAILED,
        IngestionRunStatus.QUARANTINED,
    },
    # Terminal states - no outgoing transitions. A correction is a NEW
    # IngestionRun (per rule 2, nothing here is edited in place), not a
    # transition out of a terminal one.
    IngestionRunStatus.SUCCEEDED: set(),
    IngestionRunStatus.PARTIAL: set(),
    IngestionRunStatus.FAILED: set(),
    IngestionRunStatus.QUARANTINED: set(),
}


def validate_ingestion_run_transition(current: IngestionRunStatus, proposed: IngestionRunStatus) -> None:
    """Raises InvalidTransitionError if the transition isn't allowed. Returns None (no exception) if it is."""
    allowed = _INGESTION_RUN_TRANSITIONS.get(current, set())
    if proposed not in allowed:
        raise InvalidTransitionError(
            f"IngestionRun cannot transition {current.value!r} -> {proposed.value!r}. "
            f"Allowed from {current.value!r}: {sorted(a.value for a in allowed) or '(none - terminal state)'}"
        )


# ── ParcelMatch ──────────────────────────────────────────────────────────
_PARCEL_MATCH_TRANSITIONS: dict[MatchStatus, set[MatchStatus]] = {
    MatchStatus.PENDING: {MatchStatus.CONFIRMED, MatchStatus.REJECTED},
    MatchStatus.CONFIRMED: {MatchStatus.SUPERSEDED},  # a later, better match can supersede a confirmed one
    MatchStatus.REJECTED: set(),      # terminal - a new ParcelMatch row is created instead of reviving this one
    MatchStatus.SUPERSEDED: set(),    # terminal
}


def validate_parcel_match_transition(current: MatchStatus, proposed: MatchStatus) -> None:
    allowed = _PARCEL_MATCH_TRANSITIONS.get(current, set())
    if proposed not in allowed:
        raise InvalidTransitionError(
            f"ParcelMatch cannot transition {current.value!r} -> {proposed.value!r}. "
            f"Allowed from {current.value!r}: {sorted(a.value for a in allowed) or '(none - terminal state)'}"
        )


# ── CanonicalPropertyState ───────────────────────────────────────────────
_CANONICAL_STATE_TRANSITIONS: dict[CanonicalStateLifecycle, set[CanonicalStateLifecycle]] = {
    CanonicalStateLifecycle.DRAFT: {
        CanonicalStateLifecycle.RECONCILED,
        CanonicalStateLifecycle.CONTESTED,
        CanonicalStateLifecycle.HUMAN_REVIEW_REQUIRED,
    },
    CanonicalStateLifecycle.RECONCILED: {CanonicalStateLifecycle.STALE},  # only superseded by a newer version
    CanonicalStateLifecycle.CONTESTED: {
        CanonicalStateLifecycle.RECONCILED,
        CanonicalStateLifecycle.HUMAN_REVIEW_REQUIRED,
        CanonicalStateLifecycle.STALE,
    },
    CanonicalStateLifecycle.HUMAN_REVIEW_REQUIRED: {
        CanonicalStateLifecycle.RECONCILED,
        CanonicalStateLifecycle.CONTESTED,
        CanonicalStateLifecycle.STALE,
    },
    CanonicalStateLifecycle.STALE: set(),  # terminal - a new version row supersedes it
}


def validate_canonical_state_transition(current: CanonicalStateLifecycle, proposed: CanonicalStateLifecycle) -> None:
    allowed = _CANONICAL_STATE_TRANSITIONS.get(current, set())
    if proposed not in allowed:
        raise InvalidTransitionError(
            f"CanonicalPropertyState cannot transition {current.value!r} -> {proposed.value!r}. "
            f"Allowed from {current.value!r}: {sorted(a.value for a in allowed) or '(none - terminal state)'}"
        )


# ── Exception_ ───────────────────────────────────────────────────────────
# classify -> save evidence -> record outcome -> choose next action ->
# retry / fallback / quarantine / human_review
_EXCEPTION_TRANSITIONS: dict[ExceptionStatus, set[ExceptionStatus]] = {
    ExceptionStatus.OPEN: {
        ExceptionStatus.RETRIED,
        ExceptionStatus.FALLBACK_APPLIED,
        ExceptionStatus.QUARANTINED,
        ExceptionStatus.ESCALATED,
        ExceptionStatus.RESOLVED,  # a genuinely trivial exception can resolve immediately
    },
    ExceptionStatus.RETRIED: {
        ExceptionStatus.RESOLVED,
        ExceptionStatus.FALLBACK_APPLIED,
        ExceptionStatus.QUARANTINED,
        ExceptionStatus.ESCALATED,
    },
    ExceptionStatus.FALLBACK_APPLIED: {ExceptionStatus.RESOLVED, ExceptionStatus.ESCALATED},
    ExceptionStatus.QUARANTINED: {ExceptionStatus.ESCALATED, ExceptionStatus.RESOLVED},
    ExceptionStatus.ESCALATED: {ExceptionStatus.RESOLVED},  # human review concludes it
    ExceptionStatus.RESOLVED: set(),  # terminal
}


def validate_exception_transition(current: ExceptionStatus, proposed: ExceptionStatus) -> None:
    allowed = _EXCEPTION_TRANSITIONS.get(current, set())
    if proposed not in allowed:
        raise InvalidTransitionError(
            f"Exception cannot transition {current.value!r} -> {proposed.value!r}. "
            f"Allowed from {current.value!r}: {sorted(a.value for a in allowed) or '(none - terminal state)'}"
        )
