"""
multi_transform.py — try multiple plausible formats of a recorder doc number.

Sits ON TOP of a RecorderAdapter, not inside it. The adapter's contract is
"give me this exact doc number, hit or miss." This helper's job is policy:
CA recorder portals index the same underlying deed under different string
shapes depending on year, install version, or the clerk's data entry. When
the single canonical shape misses, try the plausible variants and record
which one hit — so we can either fix the norm or accept the variance.

Design note: variants are format transforms of the *raw* doc number the
adapter receives (e.g. "2022R000326"). The adapter still applies its own
per-county transform (Tehama's r_to_strip, Butte's r_to_hyphen) on top of
each variant. So the total space is variants × adapter_transform.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

from contracts import Event, IntegrityError


@dataclass
class MultiTransformResult:
    events: Sequence[Event]     # possibly empty
    variant_matched: str = ""   # which variant produced the hit (empty if none)
    tried: int = 0              # how many variants were tried
    integrity_error: str = ""   # non-empty if any variant tripped an integrity gate


def generate_doc_variants(doc: str, max_variants: int = 4) -> list[str]:
    """Generate up to `max_variants` plausible CA recorder doc-number shapes,
    priority-ordered so the most-likely variants come FIRST.

    Priority order (learned from the 2026-08-02 10-parcel batch — every hit
    matched within the first 4 variants):
      1. Raw as-is (adapter's own transform will apply)
      2. Prefix stripped (e.g. 2022R000326 -> 2022000326)
      3. Prefix stripped + leading zeros stripped (2011R0001795 -> 20111795)
      4. Digits-only (strips ID/other prefixes: 2022ID120722 -> 2022120722)

    Why cap at 4: burst-hitting the portal 9× per doc broke session state
    mid-batch. Every real hit in the first live run was in the top 4; the
    tail-end variants (2-digit year, book/page-only) never contributed a
    single match and cost ~5 wasted round-trips per parcel.
    """
    if not doc:
        return []
    doc = doc.upper().strip()
    ordered: list[str] = []
    seen: set[str] = set()

    def add(v: str) -> None:
        if v and len(v) >= 6 and v not in seen:
            seen.add(v)
            ordered.append(v)

    m = re.match(r"^(\d{4})([A-Z]+)(\d+)$", doc)
    if not m:
        add(doc)
        add(re.sub(r"[^0-9]", "", doc))                # digits only
        return ordered[:max_variants]

    year, _prefix, suffix = m.group(1), m.group(2), m.group(3)

    add(doc)                                           # raw — adapter transform may already handle
    add(f"{year}{suffix}")                             # prefix stripped
    # Tehama's modern index uses year + 6-digit padded suffix ("10-digit total").
    # 2011R0001795 (7-digit suffix) is stored under 2011001795 (6-digit padded).
    # Confirmed live 2026-08-02 batch — this variant caught a WELLS FARGO
    # ownership chain v1 missed. Third variant so it doesn't burn requests
    # on the majority of parcels that hit on variants 1-2.
    trimmed = suffix.lstrip("0")
    if trimmed:
        add(f"{year}{trimmed.zfill(6)}")
    add(re.sub(r"[^0-9]", "", doc))                    # digits only (handles ID/other prefixes)

    return ordered[:max_variants]


def search_document_with_variants(adapter, doc: str) -> MultiTransformResult:
    """Try up to 4 variants of `doc` against adapter.search_by_document_number.
    Returns on the first variant that produces at least one Event.

    Recovery: when a variant trips an IntegrityError (the results page came
    back malformed, typically a session flip after too many rapid POSTs),
    we forcibly re-do the disclaimer handshake before the next variant.
    Without this, once the session breaks every remaining variant misses
    silently — the 4-parcel regression seen in the first 10-parcel batch."""
    variants = generate_doc_variants(doc)
    tried = 0
    last_gate = ""
    for variant in variants:
        tried += 1
        try:
            events = list(adapter.search_by_document_number(variant))
        except IntegrityError as exc:
            last_gate = str(exc)
            # Force a fresh disclaimer handshake before the next variant.
            # The adapter's own _ensure_session is idempotent behind a flag;
            # we clear the flag so the next call re-runs the GET+POST.
            if hasattr(adapter, "_session_ready"):
                adapter._session_ready = False
            continue
        if events:
            return MultiTransformResult(
                events=events,
                variant_matched=variant,
                tried=tried,
                integrity_error="",
            )
    return MultiTransformResult(
        events=(),
        variant_matched="",
        tried=tried,
        integrity_error=last_gate,
    )
