"""
Recorder graph population and query API.

Populates graph_nodes + graph_edges from recorder_chain JSON already
present in butte_auction_105_ENRICHED.csv (and same format on other
counties). Each doc becomes: person nodes for actors, doc node for the
document, parcel node for the APN, and typed edges connecting them.

Query API surfaces the signals a wholesaler cares about:
- portfolio_apn_count(owner): how many auction parcels does this person own
- portfolio_apn_balance(owner): total defaulted balance across all their parcels
- sibling_parcels(apn): other parcels owned by the same grantee
- shared_grantors(apn): parcels sharing a grantor (transfer network)
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from .db import connect


# ── name normalization ────────────────────────────────────────────────

# Strip common trust/entity/role suffixes so "SMITH JOHN TRUSTEE" and
# "SMITH JOHN" collapse to the same canonical name for graph joining.
_STRIP_SUFFIXES = re.compile(
    r"\s+(TRUSTEE|TR|EXECUTOR|EXECUTRIX|ADMINISTRATOR|JR|SR|II|III|IV|"
    r"ETAL|ET AL|CO-TRUSTEE|SUCCESSOR TRUSTEE|SUCCESSOR)$",
    re.IGNORECASE,
)
_NON_WORD = re.compile(r"[^\w\s]")


def canonical_name(raw: str) -> str:
    """Uppercase, punctuation-stripped, suffix-trimmed, whitespace-normalized.
    Applied uniformly so 'Smith, John Jr.' and 'SMITH JOHN JR' collapse."""
    if not raw:
        return ""
    s = str(raw).upper().strip()
    s = _NON_WORD.sub(" ", s)
    s = " ".join(s.split())
    prev = None
    while s != prev:
        prev = s
        s = _STRIP_SUFFIXES.sub("", s).strip()
    return s


def entity_kind(canonical: str) -> str:
    """Classify a canonical name as person vs entity."""
    if not canonical:
        return "unknown"
    tokens = set(canonical.split())
    entity_markers = {"LLC", "INC", "CORP", "CORPORATION", "COMPANY", "TRUST",
                      "ESTATE", "HOLDINGS", "PROPERTIES", "ASSOCIATION",
                      "PARTNERSHIP", "LP", "TR", "REVOCABLE"}
    if tokens & entity_markers:
        return "entity"
    return "person"


# ── write helpers ─────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _upsert_node(
    conn,
    node_kind: str,
    canonical: str | None = None,
    display: str | None = None,
    apn: str | None = None,
    doc_number: str | None = None,
    county: str | None = None,
    extra: dict | None = None,
) -> int:
    """Get-or-create a node by its natural key."""
    now = _now()
    # Look up existing
    row = conn.execute(
        """
        SELECT id FROM graph_nodes
         WHERE node_kind = ?
           AND (canonical_name IS ? OR canonical_name = ?)
           AND (apn IS ? OR apn = ?)
           AND (doc_number IS ? OR doc_number = ?)
           AND (county IS ? OR county = ?)
        """,
        (node_kind,
         canonical, canonical or "",
         apn, apn or "",
         doc_number, doc_number or "",
         county, county or ""),
    ).fetchone()
    if row:
        # Update last_seen
        conn.execute("UPDATE graph_nodes SET last_seen = ? WHERE id = ?", (now, row["id"]))
        return row["id"]
    # Insert
    cur = conn.execute(
        """
        INSERT INTO graph_nodes
            (node_kind, canonical_name, display_name, apn, doc_number, county, first_seen, last_seen, extra_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (node_kind, canonical, display, apn, doc_number, county, now, now,
         json.dumps(extra) if extra else None),
    )
    return cur.lastrowid


def _upsert_edge(conn, from_id: int, to_id: int, edge_kind: str, doc_id: int | None = None) -> None:
    now = _now()
    row = conn.execute(
        """
        SELECT id FROM graph_edges
         WHERE from_node_id = ? AND to_node_id = ? AND edge_kind = ?
           AND (doc_id IS ? OR doc_id = ?)
        """,
        (from_id, to_id, edge_kind, doc_id, doc_id or 0),
    ).fetchone()
    if row:
        conn.execute("UPDATE graph_edges SET last_seen = ? WHERE id = ?", (now, row["id"]))
        return
    conn.execute(
        """
        INSERT INTO graph_edges (from_node_id, to_node_id, edge_kind, doc_id, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (from_id, to_id, edge_kind, doc_id, now, now),
    )


# ── population ────────────────────────────────────────────────────────

def populate_from_chain(chain_json: str, apn: str, county: str = "butte") -> dict:
    """Populate the graph from one parcel's recorder_chain JSON blob.
    Returns counts (nodes_created, edges_created) for reporting."""
    if not chain_json or chain_json.strip() in ("", "[]", "None", "nan"):
        return {"nodes_created": 0, "edges_created": 0}

    try:
        chain = json.loads(chain_json)
    except json.JSONDecodeError:
        return {"nodes_created": 0, "edges_created": 0, "error": "invalid_json"}

    if not chain:
        return {"nodes_created": 0, "edges_created": 0}

    conn = connect()
    nodes_before = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
    edges_before = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]

    parcel_id = _upsert_node(conn, "parcel", apn=apn, county=county, display=apn)

    for entry in chain:
        doc_number = entry.get("doc_number", "")
        if not doc_number:
            continue
        doc_id = _upsert_node(
            conn, "doc",
            doc_number=doc_number,
            county=county,
            display=f"{entry.get('doc_type','?')} {doc_number}",
            extra={
                "doc_type": entry.get("doc_type"),
                "recording_date": entry.get("recording_date"),
                "book_page": entry.get("book_page"),
            },
        )
        _upsert_edge(conn, doc_id, parcel_id, "affects", doc_id=doc_id)

        for grantor_raw in entry.get("grantors", []) or []:
            canon = canonical_name(grantor_raw)
            if not canon:
                continue
            kind = entity_kind(canon)
            person_id = _upsert_node(conn, kind, canonical=canon, display=grantor_raw)
            _upsert_edge(conn, person_id, doc_id, "grantor", doc_id=doc_id)

        for grantee_raw in entry.get("grantees", []) or []:
            canon = canonical_name(grantee_raw)
            if not canon:
                continue
            kind = entity_kind(canon)
            person_id = _upsert_node(conn, kind, canonical=canon, display=grantee_raw)
            _upsert_edge(conn, person_id, doc_id, "grantee", doc_id=doc_id)

    conn.commit()
    nodes_after = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
    edges_after = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
    conn.close()
    return {
        "nodes_created": nodes_after - nodes_before,
        "edges_created": edges_after - edges_before,
    }


def populate_from_csv(csv_path: str, chain_col: str = "recorder_chain",
                      apn_col: str = "auction_apn_dashed", county: str = "butte") -> dict:
    """Populate graph from every row in a CSV with a recorder_chain column."""
    df = pd.read_csv(csv_path, dtype=str)
    stats = {"parcels_seen": 0, "parcels_populated": 0, "nodes_created": 0, "edges_created": 0}
    for _, row in df.iterrows():
        stats["parcels_seen"] += 1
        chain = row.get(chain_col) or ""
        apn = row.get(apn_col) or ""
        if not apn or chain.strip() in ("", "[]", "nan", "None"):
            continue
        result = populate_from_chain(chain, apn, county=county)
        if result["nodes_created"] > 0 or result["edges_created"] > 0:
            stats["parcels_populated"] += 1
        stats["nodes_created"] += result["nodes_created"]
        stats["edges_created"] += result["edges_created"]
    return stats


# ── query API: portfolio + network ────────────────────────────────────

@dataclass
class PortfolioRow:
    owner_canonical: str
    owner_display: str
    apn_count: int
    apns: list[str]


def portfolio_by_owner(county: str = "butte", min_apn_count: int = 1) -> list[PortfolioRow]:
    """
    For every person/entity in the graph, how many parcels do they own
    (are a grantee on)? Only counts parcels in the given county.
    """
    conn = connect()
    rows = conn.execute(
        """
        SELECT p.id AS person_id, p.canonical_name, p.display_name, parcel.apn
          FROM graph_nodes p
          JOIN graph_edges e_pg ON e_pg.from_node_id = p.id AND e_pg.edge_kind = 'grantee'
          JOIN graph_nodes doc  ON doc.id = e_pg.to_node_id AND doc.node_kind = 'doc'
          JOIN graph_edges e_dp ON e_dp.from_node_id = doc.id AND e_dp.edge_kind = 'affects'
          JOIN graph_nodes parcel ON parcel.id = e_dp.to_node_id AND parcel.node_kind = 'parcel'
                                 AND parcel.county = ?
         WHERE p.node_kind IN ('person', 'entity')
        """,
        (county,),
    ).fetchall()
    conn.close()

    by_person: dict[int, PortfolioRow] = {}
    for r in rows:
        pid = r["person_id"]
        if pid not in by_person:
            by_person[pid] = PortfolioRow(
                owner_canonical=r["canonical_name"],
                owner_display=r["display_name"],
                apn_count=0,
                apns=[],
            )
        if r["apn"] not in by_person[pid].apns:
            by_person[pid].apns.append(r["apn"])
            by_person[pid].apn_count += 1

    return sorted(
        [row for row in by_person.values() if row.apn_count >= min_apn_count],
        key=lambda p: -p.apn_count,
    )


def apns_owned_by(canonical: str, county: str = "butte") -> list[str]:
    """All APNs where `canonical` name appears as a grantee."""
    conn = connect()
    rows = conn.execute(
        """
        SELECT DISTINCT parcel.apn
          FROM graph_nodes p
          JOIN graph_edges e_pg ON e_pg.from_node_id = p.id AND e_pg.edge_kind = 'grantee'
          JOIN graph_nodes doc  ON doc.id = e_pg.to_node_id
          JOIN graph_edges e_dp ON e_dp.from_node_id = doc.id AND e_dp.edge_kind = 'affects'
          JOIN graph_nodes parcel ON parcel.id = e_dp.to_node_id AND parcel.node_kind = 'parcel'
                                 AND parcel.county = ?
         WHERE p.canonical_name = ?
        """,
        (county, canonical),
    ).fetchall()
    conn.close()
    return [r["apn"] for r in rows]


def graph_summary(county: str = "butte") -> dict:
    conn = connect()
    row = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM graph_nodes WHERE node_kind = 'person') AS persons,
            (SELECT COUNT(*) FROM graph_nodes WHERE node_kind = 'entity') AS entities,
            (SELECT COUNT(*) FROM graph_nodes WHERE node_kind = 'parcel' AND county = ?) AS parcels,
            (SELECT COUNT(*) FROM graph_nodes WHERE node_kind = 'doc' AND county = ?) AS docs,
            (SELECT COUNT(*) FROM graph_edges) AS edges
        """,
        (county, county),
    ).fetchone()
    conn.close()
    return dict(row)


if __name__ == "__main__":
    import argparse, sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="CSV with recorder_chain column")
    parser.add_argument("--apn-col", default="auction_apn_dashed")
    parser.add_argument("--chain-col", default="recorder_chain")
    parser.add_argument("--county", default="butte")
    parser.add_argument("--report", action="store_true", help="Print portfolio report after populate")
    args = parser.parse_args()

    print(f"Populating graph from {args.csv}...")
    stats = populate_from_csv(args.csv, args.chain_col, args.apn_col, args.county)
    print(f"  parcels seen:      {stats['parcels_seen']}")
    print(f"  parcels populated: {stats['parcels_populated']}")
    print(f"  nodes created:     {stats['nodes_created']}")
    print(f"  edges created:     {stats['edges_created']}")
    print()
    print("Graph summary:", graph_summary(args.county))

    if args.report:
        print()
        print("Portfolio owners (>=2 parcels):")
        for row in portfolio_by_owner(county=args.county, min_apn_count=2):
            print(f"  {row.apn_count}x  {row.owner_display:35s}  APNs: {row.apns}")
