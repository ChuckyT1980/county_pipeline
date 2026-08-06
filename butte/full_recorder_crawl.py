"""
Full Butte County recorder crawl by owner name.

For each unique owner in the current call sheet:
- Submit a Tyler name search
- Paginate all results
- Extract every document (doc#, type, date, grantors, grantees)
- Populate graph_nodes + graph_edges

This is what turns the graph from "89 docs per current parcel" into a
real cross-parcel actor network. Unlocks:
- All docs where an owner appears (deeds, DoTs, liens, NODs, reconveyances)
- Business partners (co-grantees)
- Historical distress (past tax liens, IRS liens, judgments)
- Portfolio detection across all of Butte, not just the auction cohort

Uses the existing httpx-based tyler_recorder_client (NOT Playwright).
Rate: ~2-4 sec per name × ~3 pages average = ~10 sec per owner.
"""
import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tyler_recorder_client import TylerRecorderClient, BUTTE
from verification.db import connect
from verification.graph import canonical_name, entity_kind, _upsert_node, _upsert_edge
from verification.writer import VerificationRun


PAGE_DELAY = 0.6         # between paginated result pulls
NAME_DELAY = 1.5         # between different name searches (be a good citizen)
MAX_PAGES_PER_NAME = 10  # hard stop — common surnames blow past this
CHECKPOINT_PATH = os.path.join(os.path.dirname(__file__), "full_recorder_crawl_checkpoint.json")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def unique_owner_names(csv_path: str, owner_col: str = "verified_current_owner_name") -> list[str]:
    df = pd.read_csv(csv_path, dtype=str)
    seen = set()
    out = []
    for name in df[owner_col].dropna():
        n = str(name).strip()
        if n and n.lower() != "nan" and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def load_checkpoint() -> dict:
    if not os.path.exists(CHECKPOINT_PATH):
        return {"completed_names": [], "docs_extracted": 0, "started_at": _now()}
    with open(CHECKPOINT_PATH, "r") as f:
        return json.load(f)


def save_checkpoint(state: dict) -> None:
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(state, f, indent=2)


def crawl_one_name(client: TylerRecorderClient, name: str) -> tuple[list, int]:
    """Fetch all pages of results for a name. Returns (all_results, total_reported)."""
    try:
        client.submit_name_search(name)
        all_results = []
        first_page, total = client.get_results(search_type="name", page=1)
        all_results.extend(first_page)
        if total > len(first_page):
            pages_needed = min(MAX_PAGES_PER_NAME, (total // max(1, len(first_page))) + 1)
            for page in range(2, pages_needed + 1):
                more, _ = client.get_results(search_type="name", page=page)
                if not more:
                    break
                all_results.extend(more)
                time.sleep(PAGE_DELAY)
        return all_results, total
    except Exception as e:
        print(f"    ERROR on '{name}': {type(e).__name__}: {str(e)[:100]}")
        return [], 0


def persist_docs(docs: list, county: str = "butte") -> tuple[int, int]:
    """Write docs + actors to the graph. Returns (docs_written, edges_written)."""
    if not docs:
        return 0, 0
    conn = connect()
    docs_before = conn.execute("SELECT COUNT(*) FROM graph_nodes WHERE node_kind='doc'").fetchone()[0]
    edges_before = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]

    for r in docs:
        if not r.doc_number:
            continue
        doc_id = _upsert_node(
            conn, "doc",
            doc_number=r.doc_number,
            county=county,
            display=f"{r.doc_type} {r.doc_number}",
            extra={
                "doc_type": r.doc_type,
                "recording_date": r.recording_date,
                "book_page": r.book_page,
            },
        )
        for grantor_raw in r.grantors or []:
            canon = canonical_name(grantor_raw)
            if canon:
                pid = _upsert_node(conn, entity_kind(canon), canonical=canon, display=grantor_raw)
                _upsert_edge(conn, pid, doc_id, "grantor", doc_id=doc_id)
        for grantee_raw in r.grantees or []:
            canon = canonical_name(grantee_raw)
            if canon:
                pid = _upsert_node(conn, entity_kind(canon), canonical=canon, display=grantee_raw)
                _upsert_edge(conn, pid, doc_id, "grantee", doc_id=doc_id)

    conn.commit()
    docs_after = conn.execute("SELECT COUNT(*) FROM graph_nodes WHERE node_kind='doc'").fetchone()[0]
    edges_after = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
    conn.close()
    return docs_after - docs_before, edges_after - edges_before


def run(csv_path: str, county: str = "butte", limit: int | None = None,
        resume: bool = True) -> None:
    names = unique_owner_names(csv_path)
    if limit:
        names = names[:limit]

    checkpoint = load_checkpoint() if resume else {"completed_names": [], "docs_extracted": 0, "started_at": _now()}
    completed = set(checkpoint["completed_names"])
    todo = [n for n in names if n not in completed]

    print(f"Full recorder crawl for {county}")
    print(f"  Total unique owner names: {len(names)}")
    print(f"  Already completed:        {len(completed)}")
    print(f"  Remaining:                {len(todo)}")

    if not todo:
        print("Nothing to do.")
        return

    client = TylerRecorderClient(BUTTE)
    start = time.time()

    with VerificationRun(
        county=county,
        cycle_label="butte full recorder crawl (name expansion)",
        input_source=csv_path,
        parcel_count=len(names),
    ) as run_ctx:
        print(f"Verification run #{run_ctx.run_id}")

        try:
            for i, name in enumerate(todo, start=1):
                elapsed = time.time() - start
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (len(todo) - i) / rate if rate > 0 else 0
                print(f"[{i}/{len(todo)}] {name[:40]:40s} (elapsed {elapsed/60:.1f}m, ETA {remaining/60:.1f}m)")

                results, total_reported = crawl_one_name(client, name)
                docs_written, edges_written = persist_docs(results, county=county)

                checkpoint["completed_names"].append(name)
                checkpoint["docs_extracted"] += len(results)
                save_checkpoint(checkpoint)

                print(f"    -> {len(results)} docs fetched (of {total_reported} total), {docs_written} new docs, {edges_written} new edges")

                # Record aggregate stats to verification
                run_ctx.record_field(
                    apn=f"OWNER:{name[:40]}",     # abusing apn field for owner-level provenance
                    field_name="recorder_docs_count",
                    field_value=str(len(results)),
                    source="tyler_recorder_name_search",
                    confidence=0.9,
                    notes=f"total_reported={total_reported}",
                )

                time.sleep(NAME_DELAY)

        finally:
            client.close()

    print()
    print(f"Crawl complete.")
    print(f"  Total elapsed:      {(time.time()-start)/60:.1f} min")
    print(f"  Names crawled:      {len(todo)}")
    print(f"  Docs in checkpoint: {checkpoint['docs_extracted']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"))
    parser.add_argument("--limit", type=int, default=None, help="Crawl only first N unique names (smoke test)")
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint, start fresh")
    args = parser.parse_args()
    run(args.csv, limit=args.limit, resume=not args.no_resume)
