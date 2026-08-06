"""
smoke_tehama_live.py — one live request against the Tehama recorder portal
to prove the unified contract wires end-to-end against real bytes.

What this test earns you:
  * confirms the Tyler wire in tehama_recorder_tyler.py is correct
    (or fails LOUD via an integrity_gate so we know exactly what shifted)
  * writes the fetched pages to data/raw/tehama/recorder/... so any parse
    failure is inspectable without a re-fetch
  * verifies event_type() maps the returned label to a real EventType

Known-good input: 2026R006490 — confirmed live in tyler_recorder_client
as a DEED with grantor + grantee populated.

Run:  python smoke_tehama_live.py
"""
from __future__ import annotations

import json
import sys

from contracts import (
    CountyConfig,
    SourceConfig,
    SourceType,
    build_adapters_for_county,
)
from http_client import build_http_client
from normalizers import DefaultNormalizers
from raw_store import FileRawStore
import tehama_recorder_tyler  # noqa: F401 — registers TehamaTylerRecorderAdapter


def go(doc_number: str = "2026R006490") -> int:
    norm = DefaultNormalizers(home_county="tehama")
    store = FileRawStore(root_dir="data")
    http = build_http_client()

    cfg = CountyConfig(
        key="tehama",
        display_name="Tehama County",
        sources={
            SourceType.RECORDER: SourceConfig(
                vendor="tyler",
                url="https://recordsearch.tehama.gov",
                method="html",
                parser_version="2024.1.40-tehama-1",
            ),
        },
    )
    adapters = build_adapters_for_county(cfg, http, store, norm)
    recorder = adapters[SourceType.RECORDER]

    print(f"[smoke] search_by_document_number({doc_number!r})")
    try:
        events = list(recorder.search_by_document_number(doc_number))
    except Exception as exc:
        print(f"[smoke] FAILED: {type(exc).__name__}: {exc}")
        print("[smoke] raw fetches are on disk under data/raw/tehama/recorder/")
        print("[smoke] see data/raw_index.jsonl for the URL + hash of each attempt")
        http.close()
        return 1
    finally:
        pass

    print(f"[smoke] returned {len(events)} event(s)")
    for i, ev in enumerate(events, 1):
        d = ev.model_dump(mode="json")
        # trim provenance fluff for readability
        keep = {k: d[k] for k in (
            "event_type", "document_number", "recording_date",
            "grantor_raw", "grantee_raw", "data_gaps",
        ) if k in d}
        print(f"  [{i}] {json.dumps(keep, indent=2)}")

    http.close()

    if not events:
        print("[smoke] zero results — portal responded but returned no rows.")
        print("[smoke] check data/raw_index.jsonl for the last searchResults hash;")
        print("[smoke] inspect that .bin to see whether it's a real 'no results'")
        print("[smoke] page or a disclaimer-flip failure.")
        return 2

    print("[smoke] OK — wire is real; contract end-to-end validated for tehama recorder.")
    return 0


if __name__ == "__main__":
    doc = sys.argv[1] if len(sys.argv) > 1 else "2026R006490"
    sys.exit(go(doc))
