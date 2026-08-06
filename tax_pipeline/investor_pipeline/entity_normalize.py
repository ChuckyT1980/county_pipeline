"""Normalize grantee names into stable entity identifiers.

Heuristics:
    - Uppercase, strip punctuation, collapse whitespace.
    - Standardize common business suffixes (LLC, LP, INC, TRUST, etc.)
    - Classify entity type from normalized name.
    - Optional light fuzzy matching via difflib for obvious merges.

Usage:
    from investor_pipeline.entity_normalize import normalize_entity, classify_entity_type

    entity_name_normalized = normalize_entity("John A. Smith, LLC")
    entity_type = classify_entity_type(entity_name_normalized)
"""

import re
import hashlib
from typing import Optional

# ── Suffix standardization map ────────────────────────────────────────────
_SUFFIX_MAP = {
    "L L C": "LLC",
    "L.L.C.": "LLC",
    "L C": "LLC",
    "L.L.C": "LLC",
    "LIMITED LIABILITY COMPANY": "LLC",
    "LIMITED LIABILTY COMPANY": "LLC",
    "LTD LIABILITY CO": "LLC",
    "LTD LIABILTY CO": "LLC",

    "L P": "LP",
    "L.P.": "LP",
    "LIMITED PARTNERSHIP": "LP",

    "I N C": "INC",
    "I.N.C.": "INC",
    "INCORPORATED": "INC",
    "INCORPORATED": "INC",

    "T R": "TRUST",
    "T.R.": "TRUST",

    "L L P": "LLP",
    "L.L.P.": "LLP",
    "REGISTERED LIMITED LIABILITY PARTNERSHIP": "LLP",
}

# ── Entity type classification keywords ───────────────────────────────────
_LLC_CORP_KEYWORDS = [
    " LLC", " L.L.C.", " L.C.", " L L C",
    " INC", " CORP", " CORPORATION", " COMPANY", " CO ",
    " LTD", " LIMITED", " LP", " L.P.", " L L P", " L.L.P.",
    " PLLC", " P.C.",
]

_TRUST_KEYWORDS = [
    " TRUST", " TR ", " TRUSTEE", " TRUSTEES",
    " TRUST U/A", " TRUST U/D/T",
    " FAMILY TRUST", " REVOCABLE TRUST", " IRREVOCABLE TRUST",
    " LIVING TRUST", " SURVIVORS TRUST",
    " TRUST AGREEMENT", " TRUST DATED",
]

_OTHER_KEYWORDS = [
    " ESTATE ", " ESTATE OF",
    " CITY OF", " COUNTY OF", " STATE OF",
    " UNITED STATES", " US BANKRUPTCY",
    " CHURCH", " MINISTRY", " FELLOWSHIP",
    " SCHOOL DISTRICT", " COMMUNITY COLLEGE",
    " HOA", " HOMEOWNERS ASSOCIATION",
    " NONPROFIT", " NON-PROFIT", " INCORPORATED",
]

# ── Punctuation to strip (keep spaces, letters, digits) ───────────────────
_STRIP_RE = re.compile(r"[^A-Z0-9 &./#'-]")
_MULTI_SPACE_RE = re.compile(r"\s+")


def normalize_entity(raw: str) -> str:
    """Normalize a grantee name to a stable, mergeable string."""
    s = raw.strip().upper()

    # Remove common vesting debris
    s = re.sub(
        r"\b(A MARRIED MAN|A MARRIED WOMAN|AN UNMARRIED MAN|AN UNMARRIED WOMAN|"
        r"AS SOLE TRUSTEE|AS TRUSTEE|AS TRUSTEES|"
        r"AND|&|THE\b)",
        " ", s, flags=re.IGNORECASE
    )

    # Strip punctuation except periods (needed for suffix detection)
    s = _STRIP_RE.sub(" ", s)
    s = _MULTI_SPACE_RE.sub(" ", s).strip()

    # Standardize known suffix variants
    for variant, canonical in sorted(_SUFFIX_MAP.items(), key=lambda x: -len(x[0])):
        pattern = r"\b" + re.escape(variant) + r"\b"
        s = re.sub(pattern, canonical, s, flags=re.IGNORECASE)

    # Compact whitespace again after substitutions
    s = _MULTI_SPACE_RE.sub(" ", s).strip()

    return s


def classify_entity_type(normalized_name: str) -> str:
    """Heuristic classification: INDIVIDUAL, LLC_CORP, TRUST, or OTHER."""
    name = " " + normalized_name + " "

    for kw in _OTHER_KEYWORDS:
        if kw in name:
            return "OTHER"

    for kw in _TRUST_KEYWORDS:
        if kw in name:
            return "TRUST"

    for kw in _LLC_CORP_KEYWORDS:
        if kw in name:
            return "LLC_CORP"

    return "INDIVIDUAL"


def entity_id(normalized_name: str) -> str:
    """Stable hash-based entity ID."""
    return hashlib.sha256(normalized_name.encode()).hexdigest()[:16]


def pick_representative_name(names: list) -> str:
    """From a list of raw names for the same entity, pick the longest
    non-empty string as the representative."""
    valid = [n for n in names if n.strip()]
    if not valid:
        return ""
    return max(valid, key=len)


def fuzzy_merge_candidates(normalized_names: list, threshold: float = 0.85):
    """Yield pairs of (name_a, name_b, score) for names that are
    similar enough to merge.  Lightweight helper; not called automatically.

    Usage:
        for a, b, score in fuzzy_merge_candidates(all_names):
            print(f"{a} ~ {b} ({score:.2f})")
    """
    import difflib
    seen = set()
    for i, a in enumerate(normalized_names):
        for j, b in enumerate(normalized_names):
            if i >= j:
                continue
            key = tuple(sorted([a, b]))
            if key in seen:
                continue
            seen.add(key)
            score = difflib.SequenceMatcher(None, a, b).ratio()
            if score >= threshold:
                yield a, b, score
