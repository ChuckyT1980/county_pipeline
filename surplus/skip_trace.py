"""
Provider-agnostic skip trace.

Ships three adapters:
    StubAdapter                — always returns "not implemented, plug in provider"
    ManualAdapter              — reads results from a chuck-maintained CSV (for manually-traced leads)
    BatchSkipTracingAdapter    — hits the BatchSkipTracing API (needs API key)

Add a new provider by implementing the SkipTraceAdapter protocol and
registering it in ADAPTERS. Everything else in the pipeline stays the same.

Usage:
    from surplus.skip_trace import get_adapter, trace_and_persist

    adapter = get_adapter()  # reads env: SKIP_TRACE_PROVIDER
    result = trace_and_persist(surplus_id, name, last_known_address, adapter)
"""
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Protocol

import requests

from .db import connect, now


# ── Data model ──────────────────────────────────────────────────────────

@dataclass
class Phone:
    number: str
    type: str = "unknown"     # mobile / landline / voip / unknown
    confidence: float = 0.5


@dataclass
class Relative:
    name: str
    relation: str = "unknown"  # spouse / child / sibling / parent / unknown
    age: int | None = None


@dataclass
class TraceResult:
    provider: str
    hit: bool = False
    current_address: str = ""
    current_city_state: str = ""
    phones: list[Phone] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    relatives: list[Relative] = field(default_factory=list)
    age: int | None = None
    is_deceased: bool = False
    date_of_death: str = ""
    confidence: float = 0.0
    cost_cents: int = 0
    raw_response: dict = field(default_factory=dict)

    def to_json_bits(self) -> dict:
        return {
            "phones_json": json.dumps([asdict(p) for p in self.phones]),
            "emails_json": json.dumps(self.emails),
            "relatives_json": json.dumps([asdict(r) for r in self.relatives]),
            "raw_response_json": json.dumps(self.raw_response) if self.raw_response else None,
        }


# ── Adapter protocol ────────────────────────────────────────────────────

class SkipTraceAdapter(Protocol):
    name: str

    def trace(self, canonical_name: str, last_known_address: str,
              dob: str | None = None) -> TraceResult:
        ...


class StubAdapter:
    """No-op adapter for testing pipeline before a provider is signed up.
    Returns a valid but empty TraceResult so downstream code doesn't crash."""
    name = "stub"

    def trace(self, canonical_name: str, last_known_address: str, dob=None) -> TraceResult:
        return TraceResult(
            provider="stub",
            hit=False,
            confidence=0.0,
            cost_cents=0,
        )


class ManualAdapter:
    """Reads results from a CSV chuck maintains manually. Useful for the
    first ~20 leads where you want to research by hand (obit search + LinkedIn
    + county probate) rather than pay for automated trace. CSV columns:
        canonical_name, last_known_address, current_address, phones, emails,
        is_deceased (0/1), notes"""
    name = "manual"

    def __init__(self, csv_path: str):
        import pandas as pd
        self.df = pd.read_csv(csv_path, dtype=str) if os.path.exists(csv_path) else None

    def trace(self, canonical_name: str, last_known_address: str, dob=None) -> TraceResult:
        if self.df is None:
            return TraceResult(provider="manual", hit=False)
        match = self.df[
            (self.df["canonical_name"].str.upper() == canonical_name.upper())
        ]
        if len(match) == 0:
            return TraceResult(provider="manual", hit=False)
        row = match.iloc[0]
        phones_raw = str(row.get("phones", "") or "")
        emails_raw = str(row.get("emails", "") or "")
        return TraceResult(
            provider="manual",
            hit=True,
            current_address=str(row.get("current_address", "") or ""),
            phones=[Phone(number=p.strip()) for p in phones_raw.split(",") if p.strip()],
            emails=[e.strip() for e in emails_raw.split(",") if e.strip()],
            is_deceased=str(row.get("is_deceased", "")).strip() == "1",
            confidence=0.95,   # manual research is high confidence
            cost_cents=0,
            raw_response={"notes": str(row.get("notes", "") or "")},
        )


class BatchSkipTracingAdapter:
    """Real BatchSkipTracing API. Requires env: BST_API_KEY.

    IMPORTANT: This is SCAFFOLDED to match BatchSkipTracing's documented
    contract but has NOT been tested against the live API. When chuck signs
    up, verify the field names + auth pattern against the current docs
    before running against production data.

    Docs: https://batchskiptracing.com/api-documentation
    """
    name = "batchskiptracing"
    API_URL = "https://api.batchskiptracing.com/v1/skip/trace"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("BST_API_KEY")
        if not self.api_key:
            raise ValueError("BatchSkipTracing requires BST_API_KEY env var")

    def trace(self, canonical_name: str, last_known_address: str, dob=None) -> TraceResult:
        # Split name into first/last for the API
        parts = canonical_name.split()
        first_name = parts[0] if parts else ""
        last_name = parts[-1] if len(parts) > 1 else ""

        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "address": last_known_address,
        }
        if dob:
            payload["dob"] = dob

        try:
            resp = requests.post(
                self.API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return TraceResult(
                provider="batchskiptracing",
                hit=False,
                raw_response={"error": f"{type(e).__name__}: {str(e)[:200]}"},
            )

        # Adapt returned schema to our TraceResult
        person = data.get("person", {}) or {}
        phones = [
            Phone(number=p.get("number", ""), type=p.get("type", "unknown"),
                  confidence=float(p.get("confidence", 0.7)))
            for p in (person.get("phones") or [])
        ]
        emails = [e.get("address", "") for e in (person.get("emails") or []) if e.get("address")]
        relatives = [
            Relative(name=r.get("name", ""), relation=r.get("relation", "unknown"),
                     age=r.get("age"))
            for r in (person.get("relatives") or [])
        ]

        return TraceResult(
            provider="batchskiptracing",
            hit=bool(phones or emails or person.get("current_address")),
            current_address=person.get("current_address", ""),
            current_city_state=person.get("current_city_state", ""),
            phones=phones,
            emails=emails,
            relatives=relatives,
            age=person.get("age"),
            is_deceased=bool(person.get("is_deceased")),
            date_of_death=person.get("date_of_death", ""),
            confidence=float(person.get("confidence", 0.7)),
            cost_cents=20,  # ~$0.20 per lookup
            raw_response=data,
        )


ADAPTERS = {
    "stub": StubAdapter,
    "manual": ManualAdapter,
    "batchskiptracing": BatchSkipTracingAdapter,
}


def get_adapter(provider: str | None = None, **kwargs) -> SkipTraceAdapter:
    """Returns the configured adapter. Reads SKIP_TRACE_PROVIDER env if no arg."""
    provider = provider or os.environ.get("SKIP_TRACE_PROVIDER", "stub")
    cls = ADAPTERS.get(provider)
    if cls is None:
        raise ValueError(f"Unknown skip-trace provider: {provider}. Options: {list(ADAPTERS)}")
    if provider == "stub":
        return cls()
    if provider == "manual":
        csv_path = kwargs.get("csv_path") or os.environ.get("SKIP_TRACE_MANUAL_CSV", "manual_traces.csv")
        return cls(csv_path)
    if provider == "batchskiptracing":
        return cls(kwargs.get("api_key"))
    return cls()


# ── Persistence ─────────────────────────────────────────────────────────

def trace_and_persist(surplus_id: int, canonical_name: str,
                       last_known_address: str, adapter: SkipTraceAdapter,
                       dob: str | None = None) -> TraceResult:
    """Trace, write to skip_trace_results (upsert on canonical+addr+provider),
    write to skip_trace_ledger (audit trail), and update surplus_opportunities."""
    conn = connect()

    # Check cache first — dedupe within 90 days
    existing = conn.execute(
        """
        SELECT id FROM skip_trace_results
         WHERE canonical_name = ? AND last_known_address = ? AND provider = ?
           AND datetime(request_at) > datetime('now', '-90 days')
        """,
        (canonical_name, last_known_address or "", adapter.name),
    ).fetchone()
    if existing:
        # Reuse — still write to ledger for audit
        conn.execute(
            """INSERT INTO skip_trace_ledger (surplus_id, canonical_name, provider, cost_cents, hit, requested_at)
                 VALUES (?, ?, ?, 0, 1, ?)""",
            (surplus_id, canonical_name, adapter.name, now()),
        )
        conn.commit()
        conn.close()
        # Rehydrate as TraceResult
        row = conn2 = connect()
        r = conn2.execute(
            "SELECT * FROM skip_trace_results WHERE id = ?", (existing["id"],)
        ).fetchone()
        conn2.close()
        return _row_to_result(r)

    # Perform the trace
    result = adapter.trace(canonical_name, last_known_address, dob=dob)

    # Persist to skip_trace_results
    bits = result.to_json_bits()
    conn.execute(
        """
        INSERT INTO skip_trace_results
            (canonical_name, last_known_address, provider, request_at,
             current_address, current_city_state, phones_json, emails_json,
             relatives_json, age, is_deceased, date_of_death, confidence,
             cost_cents, raw_response_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(canonical_name, last_known_address, provider) DO UPDATE SET
            request_at = excluded.request_at,
            current_address = excluded.current_address,
            current_city_state = excluded.current_city_state,
            phones_json = excluded.phones_json,
            emails_json = excluded.emails_json,
            relatives_json = excluded.relatives_json,
            age = excluded.age,
            is_deceased = excluded.is_deceased,
            date_of_death = excluded.date_of_death,
            confidence = excluded.confidence,
            cost_cents = excluded.cost_cents,
            raw_response_json = excluded.raw_response_json
        """,
        (canonical_name, last_known_address or "", adapter.name, now(),
         result.current_address, result.current_city_state,
         bits["phones_json"], bits["emails_json"], bits["relatives_json"],
         result.age, int(result.is_deceased), result.date_of_death,
         result.confidence, result.cost_cents, bits["raw_response_json"]),
    )

    # Ledger
    conn.execute(
        """INSERT INTO skip_trace_ledger (surplus_id, canonical_name, provider, cost_cents, hit, requested_at)
             VALUES (?, ?, ?, ?, ?, ?)""",
        (surplus_id, canonical_name, adapter.name, result.cost_cents, int(result.hit), now()),
    )

    # Update surplus_opportunities
    if surplus_id:
        new_status = "traced" if result.hit else "traced_no_hit"
        conn.execute(
            """UPDATE surplus_opportunities
                  SET last_traced_at = ?, trace_cost_cents = trace_cost_cents + ?,
                      status = CASE WHEN status = 'open' THEN ? ELSE status END,
                      updated_at = ?
                WHERE id = ?""",
            (now(), result.cost_cents, new_status, now(), surplus_id),
        )
    conn.commit()
    conn.close()
    return result


def _row_to_result(row) -> TraceResult:
    if row is None:
        return TraceResult(provider="stub", hit=False)
    def _js(s):
        try:
            return json.loads(s) if s else []
        except json.JSONDecodeError:
            return []
    phones = [Phone(**p) for p in _js(row["phones_json"])]
    relatives = [Relative(**r) for r in _js(row["relatives_json"])]
    return TraceResult(
        provider=row["provider"],
        hit=True,
        current_address=row["current_address"] or "",
        current_city_state=row["current_city_state"] or "",
        phones=phones,
        emails=_js(row["emails_json"]),
        relatives=relatives,
        age=row["age"],
        is_deceased=bool(row["is_deceased"]),
        date_of_death=row["date_of_death"] or "",
        confidence=row["confidence"] or 0,
        cost_cents=0,   # cached, zero incremental cost
    )
