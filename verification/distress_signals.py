"""
Distress signal extraction from the recorder graph.

For each current auction owner, walk all their historical documents and
count meaningful signals:
    federal_tax_liens_ever      IRS lien records against them
    federal_tax_liens_released  matching Release of Federal Tax Lien (paid off)
    notices_of_default          past NODs (foreclosure track)
    notices_of_sale             past Notices of Trustee's Sale
    judgment_liens              Abstract of Judgment / Judgment Lien records
    satisfactions_received      Satisfaction of Judgment where they're grantee (they won a case)
    reconveyances               Full Reconveyances of trust deeds (debt paid off)
    deed_transfers              Grant Deeds / Trustee's Deeds naming them as grantee
    business_partners           Co-grantees on any doc — surfaces spouses, partners, corp officers

Adds columns to the CSV:
    distress_signal_score       0-100 composite
    distress_signals            comma-separated list of positive flags
    business_partners           pipe-separated names of frequent co-grantees
"""
import argparse
import json
from collections import Counter, defaultdict

import pandas as pd

from .db import connect
from .graph import canonical_name


# Doc-type buckets. Case-insensitive substring match on doc_type.
LIEN_TYPES = ["FEDERAL TAX LIEN", "STATE TAX LIEN", "ABSTRACT OF JUDGMENT", "MECHANIC LIEN", "MECHANICS LIEN", "JUDGMENT LIEN"]
LIEN_RELEASE_TYPES = ["RELEASE OF FEDERAL TAX LIEN", "RELEASE OF STATE TAX LIEN", "RELEASE OF LIEN"]
NOD_TYPES = ["NOTICE OF DEFAULT"]
NOS_TYPES = ["NOTICE OF TRUSTEE", "NOTICE OF SALE"]
SATISFACTION_TYPES = ["SATISFACTION OF JUDGMENT", "SATISFACTION"]
RECONVEYANCE_TYPES = ["RECONVEYANCE", "FULL RECONVEYANCE"]
DEED_TYPES = ["GRANT DEED", "TRUSTEE'S DEED", "TRUSTEES DEED", "WARRANTY DEED", "QUITCLAIM DEED"]
TRUST_DEED_TYPES = ["DEED OF TRUST"]
TAX_DEFAULT_TYPES = ["NOTICE OF POWER TO SELL", "NOTICE OF TAX DEFAULT", "RESCISSION OF NOTICE OF TAX DEFAULT"]


def _matches_any(doc_type: str, patterns: list) -> bool:
    dt = (doc_type or "").upper()
    return any(p.upper() in dt for p in patterns)


def signals_for_owner(canonical: str, county: str = "butte") -> dict:
    """Walk the graph for a person and count distress signals across all their docs."""
    conn = connect()

    # Find the person node
    person = conn.execute(
        "SELECT id FROM graph_nodes WHERE canonical_name = ? AND node_kind IN ('person','entity')",
        (canonical,),
    ).fetchone()
    if not person:
        conn.close()
        return {"docs_total": 0, "signals": [], "signal_counts": {}, "business_partners": []}

    person_id = person["id"]

    # All docs where person is grantor OR grantee, with doc_type
    rows = conn.execute(
        """
        SELECT DISTINCT doc.id AS doc_id, doc.doc_number, doc.extra_json, e.edge_kind AS role
          FROM graph_nodes doc
          JOIN graph_edges e ON e.to_node_id = doc.id AND e.from_node_id = ? AND e.edge_kind IN ('grantor','grantee')
         WHERE doc.node_kind = 'doc'
        """,
        (person_id,),
    ).fetchall()

    counts = Counter()
    doc_ids: list[int] = []
    for r in rows:
        doc_ids.append(r["doc_id"])
        extra = json.loads(r["extra_json"]) if r["extra_json"] else {}
        doc_type = extra.get("doc_type", "")
        role = r["role"]

        if _matches_any(doc_type, LIEN_RELEASE_TYPES):
            counts["federal_tax_liens_released"] += 1
        elif _matches_any(doc_type, LIEN_TYPES):
            counts["liens_recorded_against"] += 1

        if _matches_any(doc_type, NOD_TYPES):
            counts["notices_of_default"] += 1
        if _matches_any(doc_type, NOS_TYPES):
            counts["notices_of_sale"] += 1
        if _matches_any(doc_type, SATISFACTION_TYPES):
            # Satisfaction as grantee = they won a case; as grantor = they released one
            if role == "grantee":
                counts["satisfactions_received"] += 1
            else:
                counts["satisfactions_given"] += 1
        if _matches_any(doc_type, RECONVEYANCE_TYPES):
            counts["reconveyances"] += 1
        if _matches_any(doc_type, DEED_TYPES):
            if role == "grantee":
                counts["deeds_received"] += 1
            else:
                counts["deeds_given"] += 1
        if _matches_any(doc_type, TAX_DEFAULT_TYPES):
            counts["tax_default_events"] += 1
        if _matches_any(doc_type, TRUST_DEED_TYPES):
            if role == "grantor":
                counts["trust_deeds_borrowed"] += 1
            else:
                counts["trust_deeds_lent"] += 1

    # Business partners: for each doc where person is grantee, find other grantees
    partners_counter = Counter()
    if doc_ids:
        placeholders = ",".join("?" * len(doc_ids))
        partner_rows = conn.execute(
            f"""
            SELECT p.canonical_name, p.display_name
              FROM graph_edges e
              JOIN graph_nodes p ON p.id = e.from_node_id
             WHERE e.to_node_id IN ({placeholders})
               AND e.edge_kind = 'grantee'
               AND e.from_node_id != ?
               AND p.node_kind IN ('person','entity')
            """,
            (*doc_ids, person_id),
        ).fetchall()
        for r in partner_rows:
            partners_counter[(r["canonical_name"], r["display_name"])] += 1

    business_partners = [
        {"canonical": k[0], "display": k[1], "shared_docs": v}
        for k, v in partners_counter.most_common(10)
    ]

    conn.close()

    # Positive-signal list — used for CSV summary column
    positive_signals = []
    if counts.get("liens_recorded_against", 0) > counts.get("federal_tax_liens_released", 0):
        positive_signals.append(f"unresolved_liens({counts['liens_recorded_against'] - counts['federal_tax_liens_released']})")
    if counts.get("federal_tax_liens_released", 0) > 0:
        positive_signals.append(f"paid_liens({counts['federal_tax_liens_released']})")
    if counts.get("notices_of_default", 0) > 0:
        positive_signals.append(f"prior_nods({counts['notices_of_default']})")
    if counts.get("notices_of_sale", 0) > 0:
        positive_signals.append(f"trustee_sales({counts['notices_of_sale']})")
    if counts.get("satisfactions_received", 0) >= 2:
        positive_signals.append(f"active_creditor({counts['satisfactions_received']})")
    if counts.get("tax_default_events", 0) > 0:
        positive_signals.append(f"tax_defaults({counts['tax_default_events']})")

    return {
        "docs_total": len(doc_ids),
        "signal_counts": dict(counts),
        "signals": positive_signals,
        "business_partners": business_partners,
    }


def distress_score(signal_counts: dict) -> int:
    """Composite 0-100. Higher = more distress signal (motivated seller)."""
    score = 0
    unresolved = signal_counts.get("liens_recorded_against", 0) - signal_counts.get("federal_tax_liens_released", 0)
    score += min(30, unresolved * 10)                                # unresolved liens: 10 per, cap 30
    score += min(25, signal_counts.get("notices_of_default", 0) * 8)  # NODs
    score += min(15, signal_counts.get("notices_of_sale", 0) * 5)    # NOS
    score += min(20, signal_counts.get("tax_default_events", 0) * 4)  # tax defaults
    # A "current owner" with lots of transfers around them = more churn = maybe motivated
    score += min(10, signal_counts.get("deeds_given", 0))
    return min(100, score)


def merge_into_csv(csv_path: str, county: str = "butte",
                   owner_col: str = "verified_current_owner_name") -> None:
    df = pd.read_csv(csv_path, dtype=str)
    for col in ("distress_signal_score", "distress_signals", "distress_signal_counts", "business_partners"):
        if col not in df.columns:
            df[col] = ""

    stats = {"parcels": 0, "with_signals": 0, "no_owner": 0, "no_history": 0}

    for idx, row in df.iterrows():
        raw_owner = row.get(owner_col)
        if pd.isna(raw_owner) or not str(raw_owner).strip() or str(raw_owner).strip().lower() == "nan":
            stats["no_owner"] += 1
            continue
        canon = canonical_name(raw_owner)
        result = signals_for_owner(canon, county=county)
        if result["docs_total"] == 0:
            stats["no_history"] += 1
            continue
        score = distress_score(result["signal_counts"])
        df.at[idx, "distress_signal_score"] = str(score)
        df.at[idx, "distress_signals"] = ",".join(result["signals"])
        df.at[idx, "distress_signal_counts"] = json.dumps(result["signal_counts"])
        # Top 3 business partners
        partners = [p["display"] for p in result["business_partners"][:3]]
        df.at[idx, "business_partners"] = "|".join(partners)
        stats["parcels"] += 1
        if result["signals"]:
            stats["with_signals"] += 1

    df.to_csv(csv_path, index=False)
    print(f"Distress signals merged into {csv_path}")
    print(f"  Parcels processed:        {stats['parcels']}")
    print(f"  Parcels with signals:     {stats['with_signals']}")
    print(f"  No owner (skipped):       {stats['no_owner']}")
    print(f"  No history in graph:      {stats['no_history']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--county", default="butte")
    args = parser.parse_args()
    merge_into_csv(args.csv_path, args.county)
