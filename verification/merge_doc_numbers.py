"""
Adds recorder document numbers to the call sheet CSV so the buyer (or
you) can look up each document directly at Butte County Recorder.

Populates three pipe-separated columns per parcel from the graph's
parcel<->doc edges:
    recorder_doc_numbers   e.g. "2012-0044824|2018-0038943"
    recorder_doc_types     matching types
    recorder_doc_dates     matching dates

Only includes docs that are actually linked to the parcel (via the
"affects" edge). Name-search-only docs (from the broader crawl) are
tracked separately in the graph but are NOT included here because they
aren't parcel-attributable without individual doc-detail lookups.
"""
import argparse
import json

import pandas as pd

from .db import connect


def merge(csv_path: str, county: str = "butte") -> None:
    df = pd.read_csv(csv_path, dtype=str)
    for col in ("recorder_doc_numbers", "recorder_doc_types", "recorder_doc_dates", "recorder_doc_count"):
        if col not in df.columns:
            df[col] = ""

    conn = connect()
    stats = {"parcels_with_docs": 0, "total_docs_linked": 0, "no_docs": 0}

    for idx, row in df.iterrows():
        apn = row.get("apn")
        if pd.isna(apn) or not str(apn).strip():
            continue

        rows = conn.execute(
            """
            SELECT doc.doc_number,
                   json_extract(doc.extra_json, '$.doc_type') AS doc_type,
                   json_extract(doc.extra_json, '$.recording_date') AS rec_date
              FROM graph_nodes parcel
              JOIN graph_edges e ON e.to_node_id = parcel.id AND e.edge_kind = 'affects'
              JOIN graph_nodes doc ON doc.id = e.from_node_id
             WHERE parcel.apn = ? AND parcel.node_kind = 'parcel' AND parcel.county = ?
             ORDER BY doc.doc_number
            """,
            (apn, county),
        ).fetchall()

        if not rows:
            stats["no_docs"] += 1
            continue

        def _date_only(v):
            if not v:
                return ""
            parts = str(v).split()
            return parts[0] if parts else ""
        df.at[idx, "recorder_doc_numbers"] = "|".join(r["doc_number"] or "" for r in rows)
        df.at[idx, "recorder_doc_types"] = "|".join(r["doc_type"] or "" for r in rows)
        df.at[idx, "recorder_doc_dates"] = "|".join(_date_only(r["rec_date"]) for r in rows)
        df.at[idx, "recorder_doc_count"] = str(len(rows))
        stats["parcels_with_docs"] += 1
        stats["total_docs_linked"] += len(rows)

    conn.close()
    df.to_csv(csv_path, index=False)
    print(f"Merged doc numbers into {csv_path}")
    print(f"  Parcels with recorder docs:  {stats['parcels_with_docs']}")
    print(f"  Parcels with NO docs:        {stats['no_docs']}")
    print(f"  Total doc links added:       {stats['total_docs_linked']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv_path")
    p.add_argument("--county", default="butte")
    args = p.parse_args()
    merge(args.csv_path, args.county)
