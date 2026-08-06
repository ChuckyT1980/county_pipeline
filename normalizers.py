"""
normalizers.py — the single chokepoint where every vendor's dialect
collapses into the canonical vocabulary defined in contracts.py.

Why this is one module, not per-vendor:
    Adapters call self.norm.event_type("Grant Deed") and get EventType.GRANT_DEED.
    If Tyler labels it "GRANT DEED" and Kofile labels it "Deed, Grant", both
    routes must hit the same enum. This is where that convergence happens.
    Add a new label variant HERE, not in an adapter — that's how vendors stay
    interchangeable.

Everything here treats UNKNOWN as a first-class outcome the caller records as
a data_gap, not a silent zero. Adding false confidence upstream (e.g. mapping
"MISC" to GRANT_DEED to "smooth out" results) is the failure mode this design
is specifically built to prevent.
"""
from __future__ import annotations

import re
from typing import Optional

from contracts import EntityType, EventType, Normalizers  # noqa: F401


# --------------------------------------------------------------------------- #
# Document-label → EventType
# --------------------------------------------------------------------------- #
# Priority-ordered patterns. First match wins. Combos like "SUBSTITUTION OF
# TRUSTEE AND FULL RECONVEYANCE" hit SUBSTITUTION_OF_TRUSTEE first because it
# comes earlier in the list — that's the more actionable distress signal.
_EVENT_PATTERNS: list[tuple[EventType, re.Pattern[str]]] = [
    # Foreclosure stack — highest signal, match FIRST so combo doc types
    # ("SUB OF TRUSTEE + FULL RECONVEYANCE") pick the more actionable event.
    (EventType.NOTICE_OF_DEFAULT,
        re.compile(r"NOTICE\s+OF\s+DEFAULT|\bNOD\b", re.IGNORECASE)),
    (EventType.NOTICE_OF_TRUSTEE_SALE,
        re.compile(r"NOTICE\s+OF\s+TRUSTEE'?S?\s+SALE|\bNOTS\b|\bNTS\b", re.IGNORECASE)),
    (EventType.SUBSTITUTION_OF_TRUSTEE,
        re.compile(r"SUBSTITUTION\s+OF\s+TRUSTEE|\bSUB\.?\s+OF\s+TRUSTEE\b|\bSOT\b", re.IGNORECASE)),
    (EventType.ASSIGNMENT_OF_DOT,
        re.compile(r"ASSIGNMENT\s+(OF\s+)?(DEED\s+OF\s+TRUST|DOT|MORTGAGE)", re.IGNORECASE)),

    # Probate / death — actionable seller signal
    (EventType.AFFIDAVIT_OF_DEATH,
        re.compile(r"AFFIDAVIT\s+OF\s+DEATH|\bAOD\b", re.IGNORECASE)),
    (EventType.PROBATE_FILING,
        re.compile(r"PROBATE|LETTERS?\s+TESTAMENTARY|LETTERS?\s+OF\s+ADMIN", re.IGNORECASE)),

    # Litigation / judgment
    (EventType.LIS_PENDENS,
        re.compile(r"LIS\s+PENDENS", re.IGNORECASE)),
    (EventType.ABSTRACT_OF_JUDGMENT,
        re.compile(r"ABSTRACT\s+OF\s+JUDG(E)?MENT|\bAOJ\b", re.IGNORECASE)),

    # Liens — most specific first so MECHANICS_LIEN doesn't hit the generic LIEN rule
    (EventType.MECHANICS_LIEN,
        re.compile(r"MECHANIC'?S?\s+LIEN", re.IGNORECASE)),
    (EventType.TAX_LIEN,
        re.compile(r"TAX\s+LIEN|FEDERAL\s+TAX\s+LIEN|\bFTL\b|STATE\s+TAX\s+LIEN", re.IGNORECASE)),

    # Tax / auction stack
    (EventType.TAX_SALE_COMPLETED,
        re.compile(r"TAX\s+DEED(\s+TO\s+PURCHASER)?", re.IGNORECASE)),
    (EventType.TAX_DEFAULT,
        re.compile(r"NOTICE\s+OF\s+POWER\s+TO\s+SELL|POWER\s+TO\s+SELL|TAX\s+DEFAULT|"
                   r"NOTICE\s+OF\s+TAX\s+SALE", re.IGNORECASE)),
    (EventType.EXCESS_PROCEEDS_AVAILABLE,
        re.compile(r"EXCESS\s+PROCEEDS|NOTICE\s+OF\s+EXCESS\s+PROCEEDS", re.IGNORECASE)),

    # Reconveyance / release — payoff signals (weaker distress on their own,
    # but valuable in a chain: DOT recorded then reconveyed = equity built)
    (EventType.RECONVEYANCE,
        re.compile(r"(FULL\s+)?RECONVEYANCE", re.IGNORECASE)),

    # Deeds / DOT — deliberately BELOW the foreclosure stack so combo labels
    # like "GRANT DEED IN LIEU OF FORECLOSURE" would still classify above.
    (EventType.QUITCLAIM_DEED,
        re.compile(r"QUIT\s*CLAIM\s+DEED|\bQCD\b", re.IGNORECASE)),
    (EventType.GRANT_DEED,
        re.compile(r"GRANT\s+DEED|\bGD\b|(?<!TAX\s)DEED(?!\s+OF\s+TRUST)", re.IGNORECASE)),
    (EventType.DEED_OF_TRUST,
        re.compile(r"DEED\s+OF\s+TRUST|\bDOT\b|\bMORTGAGE\b", re.IGNORECASE)),

    # Generic release / lien — catch-all, last resort before UNKNOWN
    (EventType.RELEASE,
        re.compile(r"\bRELEASE\b", re.IGNORECASE)),
    (EventType.LIEN,
        re.compile(r"\bLIEN\b", re.IGNORECASE)),
]


def _match_event_type(label: str) -> EventType:
    """Return the first EventType whose pattern matches label, else UNKNOWN.
    Never fabricates — a label like 'MISC' or 'DOC-01' returns UNKNOWN so the
    adapter records unmapped_doc_type:<label> as a queryable gap."""
    if not label:
        return EventType.UNKNOWN
    for enum_val, pattern in _EVENT_PATTERNS:
        if pattern.search(label):
            return enum_val
    return EventType.UNKNOWN


# --------------------------------------------------------------------------- #
# APN normalization
# --------------------------------------------------------------------------- #
# CA counties use APNs like "007-340-011-000" (Tehama), "022-210-078-000" (Butte),
# "09010115" (Fresno — no dashes). Canonical form = digits-and-uppercase only,
# no separators. That's what tyler_recorder_client's Fresno note confirmed
# lives-searchably ("09010115" hits, "090-101-15" returns zero).
_APN_STRIP_RE = re.compile(r"[^0-9A-Z]")


def _normalize_apn(raw: str) -> str:
    if not raw:
        return ""
    return _APN_STRIP_RE.sub("", raw.upper())


# --------------------------------------------------------------------------- #
# Owner normalization + entity classification
# --------------------------------------------------------------------------- #
# Order matters: TRUST before GOV before CORP, because a name like
# "COUNTY OF X REVOCABLE TRUST" is a private trust with a governmental-sounding
# grantor — the TRUST tag wins.
_ENTITY_PATTERNS: list[tuple[EntityType, re.Pattern[str]]] = [
    (EntityType.LLC,
        re.compile(r"\bLLC\b|\bL\.?L\.?C\.?\b", re.IGNORECASE)),
    (EntityType.TRUST,
        re.compile(r"\bTRUST\b|\bTRUSTEE\b|\bREV(?:OCABLE)?\s+TRUST\b|"
                   r"\bLIVING\s+TRUST\b|\bFAMILY\s+TRUST\b|\bTR\b(?=\s*$|\s+\d)",
                   re.IGNORECASE)),
    (EntityType.GOV,
        re.compile(r"\bCITY\s+OF\b|\bCOUNTY\s+OF\b|\bSTATE\s+OF\b|"
                   r"\bU\.?S\.?\s+DEPT\b|\bUNITED\s+STATES\b|"
                   r"\bDEPARTMENT\s+OF\b|\bBUREAU\s+OF\b", re.IGNORECASE)),
    (EntityType.CORP,
        re.compile(r"\bINC\.?\b|\bCORP(?:ORATION)?\.?\b|\bCOMPANY\b|\bCO\.\b|"
                   r"\bLTD\.?\b|\bLIMITED\b|\bPARTNERSHIP\b|\bLP\b|\bLLP\b|"
                   r"\bBANK\b|\bN\.?A\.?\b(?=\s*$)", re.IGNORECASE)),
]


def _classify_entity(name: str) -> EntityType:
    if not name:
        return EntityType.UNKNOWN
    for enum_val, pattern in _ENTITY_PATTERNS:
        if pattern.search(name):
            return enum_val
    # Default: treat as person. Recorder data almost never contains a truly
    # unidentifiable owner — most non-entity names are people. Downstream
    # scoring can still gate on entity_type == PERSON when it matters.
    return EntityType.PERSON


_WS_RE = re.compile(r"\s+")


def _normalize_owner_name(raw: str) -> str:
    if not raw:
        return ""
    # Collapse whitespace, strip trailing punctuation, uppercase for match/dedupe.
    cleaned = _WS_RE.sub(" ", raw.strip()).upper()
    # Strip a trailing "ETAL"/"ET AL"/"ETUX" marker so joint names dedupe with
    # the same primary. Keep the fact via a downstream flag if we ever want it.
    cleaned = re.sub(r"\s+(ETAL|ET\s+AL|ETUX|ET\s+UX)\.?$", "", cleaned)
    return cleaned.rstrip(",.;: ")


# --------------------------------------------------------------------------- #
# Address normalization
# --------------------------------------------------------------------------- #
# Full geocoding is not this module's job. What downstream scoring wants from
# an address in the near term is: a clean uppercase canonical string, and
# best-effort flags for out-of-county / out-of-state. Anything requiring a
# real geocoder (lat/lng, USPS validation) belongs behind a separate service.
_CA_STATE_RE = re.compile(r"\b(CA|CALIF(ORNIA)?)\b", re.IGNORECASE)
_ANY_STATE_RE = re.compile(
    r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|"
    r"MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|"
    r"VA|WA|WV|WI|WY)\b(\s+\d{5}(-\d{4})?)?", re.IGNORECASE)


def _normalize_address(raw: str, home_county: Optional[str] = None) -> dict:
    if not raw:
        return {"situs_norm": "", "out_of_county": None, "out_of_state": None}
    situs_norm = _WS_RE.sub(" ", raw.strip()).upper().rstrip(",.;:")

    # Out-of-state: has any state abbreviation and it's NOT CA.
    out_of_state: Optional[bool] = None
    if _ANY_STATE_RE.search(situs_norm):
        out_of_state = not bool(_CA_STATE_RE.search(situs_norm))

    # Out-of-county: presence of a different CA county name substring. Cheap
    # heuristic; a real geocoder is the right long-term answer. Only flag
    # positively when we can see a county name — leave None when unknown so
    # scoring can decide whether to demote.
    out_of_county: Optional[bool] = None
    if home_county:
        home_upper = home_county.replace("_", " ").upper()
        if home_upper in situs_norm and out_of_state is not True:
            out_of_county = False

    return {
        "situs_norm": situs_norm,
        "out_of_county": out_of_county,
        "out_of_state": out_of_state,
    }


# --------------------------------------------------------------------------- #
# The public Normalizers implementation (satisfies contracts.Normalizers protocol)
# --------------------------------------------------------------------------- #
class DefaultNormalizers:
    """Default cross-vendor normalizers. Constructed with the home county so
    address() can flag out-of-county mailings without an extra parameter on
    the Protocol."""

    def __init__(self, home_county: Optional[str] = None) -> None:
        self.home_county = home_county

    def apn(self, raw: str) -> str:
        return _normalize_apn(raw)

    def address(self, raw: str) -> dict:
        return _normalize_address(raw, self.home_county)

    def owner(self, raw: str) -> tuple[str, EntityType]:
        return _normalize_owner_name(raw), _classify_entity(raw)

    def event_type(self, vendor_label: str) -> EventType:
        return _match_event_type(vendor_label)
