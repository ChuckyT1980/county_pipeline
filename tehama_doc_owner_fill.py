"""
Tehama recorder owner-fill via the doc-number bridge.

Targets: parcels with a modern (2004+) R-form current_doc_number and no
known owner. Pulls grantor/grantee names from the Tehama Tyler recorder
(DOCSEARCH4S2 + r_to_strip), imports each chunk into state immediately so
an interruption loses at most one chunk.

Usage: python tehama_doc_owner_fill.py [--limit N] [--dry-run]
"""
import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.county import CountyConfig
from core.recorder import pull_recorder_for_doc_numbers
from core.ingest import import_recorder_docs

CHUNK = 250

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = CountyConfig.load("tehama")
    con = sqlite3.connect(r"data\counties\tehama\state.sqlite")
    sql = (
        "SELECT apn, current_doc_number FROM parcels "
        "WHERE current_doc_number LIKE '%R%' "
        "AND (owner IS NULL OR owner = '') "
        "AND current_doc_number NOT LIKE '200%R%' "
        "ORDER BY apn"
    )
    if args.limit:
        sql += f" LIMIT {args.limit}"
    targets = con.execute(sql).fetchall()
    con.close()
    print(f"[tehama-fill] targets: {len(targets):,}", flush=True)

    if args.dry_run:
        print("dry-run, stopping")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("data") / "counties" / "tehama" / "recorder_fill" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    found = 0
    for i in range(0, len(targets), CHUNK):
        chunk = targets[i:i + CHUNK]
        out = out_dir / f"recorder_docs_{i:04d}.csv"
        pull_recorder_for_doc_numbers(cfg, chunk, out_path=out)
        stats = import_recorder_docs(cfg, path=out)
        got = stats.get("parcels_updated", 0)
        found += got
        done = min(i + CHUNK, len(targets))
        print(f"[tehama-fill] {done:,}/{len(targets):,} pulled, "
              f"{found:,} parcels gained names", flush=True)
        time.sleep(1.0)

    print(f"[tehama-fill] DONE: {found:,} parcels updated", flush=True)

if __name__ == "__main__":
    main()
