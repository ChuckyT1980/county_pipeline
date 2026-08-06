"""
Ingest excess proceeds lists from configured county sources.

For each county in surplus/sources.py:
  1. Download the list file(s) (PDF or HTML)
  2. Snapshot to surplus/snapshots/<county>/<basename>.<ext> for audit
  3. Parse into structured rows
  4. Upsert into surplus_opportunities (dedup on county+apn+deed_date)
  5. Compute claim_deadline_at (= deed_date + 1 year per CA R&T §4675)

Usage:
    python -m surplus.ingest                    # all counties
    python -m surplus.ingest --county mono      # just one
    python -m surplus.ingest --county mono --dry-run
"""
import argparse
import os
import re
from datetime import datetime
from pathlib import Path

import requests

from .db import connect, now
from .parsers import get_parser, add_year
from .sources import COUNTY_SOURCES, CountySource


REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_ROOT = Path(__file__).resolve().parent / "snapshots"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _canonicalize_name(name: str) -> str:
    """Uppercase, whitespace-collapsed, punctuation-stripped for graph joining."""
    if not name:
        return ""
    s = re.sub(r"[^\w\s]", " ", str(name).upper())
    return " ".join(s.split())


def _download(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, allow_redirects=True)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"    download failed: {type(e).__name__}: {str(e)[:120]}")
        return None


def _snapshot_path(county: str, url: str) -> Path:
    d = SNAPSHOT_ROOT / county
    d.mkdir(parents=True, exist_ok=True)
    filename = url.rstrip("/").split("/")[-1] or f"snapshot_{int(datetime.now().timestamp())}"
    if not filename.endswith((".pdf", ".html", ".htm", ".csv")):
        filename += ".bin"
    return d / filename


def ingest_source(source: CountySource, dry_run: bool = False) -> dict:
    """Ingest one county's list. Returns stats dict."""
    if not source.list_urls:
        return {"county": source.county, "skipped": True, "reason": "no list_urls configured (source is 'index_page' type — needs discovery pass first)"}

    stats = {
        "county": source.county,
        "urls_tried": 0,
        "urls_ok": 0,
        "rows_parsed": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "errors": [],
    }

    parser = get_parser(source.parser_key)
    conn = connect()

    # Ensure county row in county_sources table
    conn.execute(
        """INSERT INTO county_sources (county, display_name, ttc_url, excess_proceeds_url, format, processing_cadence, notes)
             VALUES (?, ?, ?, ?, ?, ?, ?)
             ON CONFLICT(county) DO UPDATE SET
                 ttc_url = excluded.ttc_url,
                 excess_proceeds_url = excluded.excess_proceeds_url,
                 format = excluded.format,
                 processing_cadence = excluded.processing_cadence,
                 notes = excluded.notes""",
        (source.county, source.display_name, source.ttc_url,
         source.list_urls[0] if source.list_urls else source.index_url,
         source.format, source.processing_cadence, source.notes),
    )

    for url in source.list_urls:
        stats["urls_tried"] += 1
        print(f"  fetching {url[:100]}...")
        content = _download(url)
        if not content:
            stats["errors"].append(f"download failed: {url}")
            continue
        stats["urls_ok"] += 1

        # Snapshot for audit
        snap_path = _snapshot_path(source.county, url)
        if not dry_run:
            with open(snap_path, "wb") as f:
                f.write(content)

        # Parse
        try:
            rows = parser(content)
        except Exception as e:
            stats["errors"].append(f"parse error for {url}: {type(e).__name__}: {str(e)[:120]}")
            continue

        stats["rows_parsed"] += len(rows)
        print(f"    parsed {len(rows)} rows")

        if dry_run:
            continue

        # Persist
        for row in rows:
            apn = row.get("apn")
            deed_date = row.get("deed_date")
            if not apn or not deed_date:
                continue
            canonical = _canonicalize_name(row.get("former_owner_raw"))
            claim_deadline = add_year(deed_date)

            result = conn.execute(
                """
                INSERT INTO surplus_opportunities
                    (county, apn, former_owner_raw, former_owner_canonical,
                     surplus_amount, min_bid, sale_price, sale_date, deed_date,
                     claim_deadline_at, source_url, source_snapshot_path,
                     source_first_seen, source_last_seen, ingested_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(county, apn, deed_date) DO UPDATE SET
                    former_owner_raw = excluded.former_owner_raw,
                    former_owner_canonical = excluded.former_owner_canonical,
                    surplus_amount = excluded.surplus_amount,
                    sale_price = excluded.sale_price,
                    source_last_seen = excluded.source_last_seen,
                    source_url = excluded.source_url,
                    source_snapshot_path = excluded.source_snapshot_path,
                    updated_at = excluded.updated_at
                """,
                (
                    source.county, apn, row.get("former_owner_raw"), canonical,
                    row.get("surplus_amount"), row.get("min_bid"), row.get("sale_price"),
                    row.get("sale_date"), deed_date, claim_deadline,
                    url, str(snap_path),
                    now(), now(), now(), now(),
                ),
            )
            if result.rowcount > 0:
                stats["rows_inserted"] += 1

    # Update county_sources with scrape run
    if not dry_run:
        conn.execute(
            "UPDATE county_sources SET last_scraped_at = ?, last_scrape_count = ? WHERE county = ?",
            (now(), stats["rows_parsed"], source.county),
        )
        conn.commit()

    conn.close()
    return stats


def ingest_all(dry_run: bool = False, county_filter: str | None = None) -> None:
    total_parsed = 0
    total_inserted = 0
    for source in COUNTY_SOURCES:
        if county_filter and source.county != county_filter:
            continue
        print(f"[{source.county}] {source.display_name}")
        stats = ingest_source(source, dry_run=dry_run)
        if stats.get("skipped"):
            print(f"    SKIPPED: {stats['reason']}")
            continue
        print(f"    parsed={stats['rows_parsed']} inserted={stats['rows_inserted']} "
              f"errors={len(stats['errors'])}")
        total_parsed += stats["rows_parsed"]
        total_inserted += stats["rows_inserted"]

    print()
    print(f"Total across counties: parsed={total_parsed}, inserted={total_inserted}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--county", default=None, help="Ingest only this one county (default: all)")
    p.add_argument("--dry-run", action="store_true", help="Parse but don't write to DB")
    args = p.parse_args()
    ingest_all(dry_run=args.dry_run, county_filter=args.county)
