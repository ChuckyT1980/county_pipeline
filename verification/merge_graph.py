"""
Merge graph-derived signals into a call sheet CSV.

Adds:
- portfolio_apn_count       — how many other auction parcels this owner controls
- portfolio_apn_balance     — total defaulted balance across their portfolio
- portfolio_sibling_apns    — pipe-separated list of the other APNs (excluding this one)

These are computed per-parcel by matching the row's owner_canonical to the
graph's grantee edges.
"""
import argparse

import pandas as pd

from .db import connect
from .graph import canonical_name


def _money_to_float(s):
    if pd.isna(s):
        return 0.0
    try:
        return float(str(s).replace("$", "").replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def merge(csv_path: str, county: str = "butte", owner_col: str = "verified_current_owner_name",
          apn_col: str = "apn", balance_col: str = "v_total_balance") -> None:
    df = pd.read_csv(csv_path, dtype=str)
    for col in ("portfolio_apn_count", "portfolio_apn_balance", "portfolio_sibling_apns"):
        if col not in df.columns:
            df[col] = ""

    # Build APN -> balance map (across the whole call sheet — the "portfolio" is only
    # measured within the current auction cycle. Extend to all-time later.)
    apn_to_bal: dict[str, float] = {}
    for _, r in df.iterrows():
        apn = r.get(apn_col)
        if apn:
            apn_to_bal[apn] = _money_to_float(r.get(balance_col))

    conn = connect()

    # For each parcel, find portfolio via canonical owner → grantee edges
    stats = {"parcels_with_portfolio": 0, "solo_parcels": 0, "no_owner": 0}

    for idx, row in df.iterrows():
        owner = row.get(owner_col)
        apn = row.get(apn_col)
        if not apn or pd.isna(owner) or not str(owner).strip() or str(owner).strip().lower() == "nan":
            stats["no_owner"] += 1
            continue

        canon = canonical_name(owner)
        # Find all APNs where this canonical owner is a grantee in-county
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
            (county, canon),
        ).fetchall()
        owned_apns = [r["apn"] for r in rows]
        sibling_apns = [a for a in owned_apns if a != apn]

        df.at[idx, "portfolio_apn_count"] = str(len(owned_apns))
        # Total balance = this parcel + siblings that are in our call sheet
        total_bal = sum(apn_to_bal.get(a, 0.0) for a in owned_apns)
        df.at[idx, "portfolio_apn_balance"] = f"{total_bal:.2f}"
        df.at[idx, "portfolio_sibling_apns"] = "|".join(sibling_apns)

        if len(owned_apns) >= 2:
            stats["parcels_with_portfolio"] += 1
        else:
            stats["solo_parcels"] += 1

    conn.close()
    df.to_csv(csv_path, index=False)

    print(f"Merged graph signals into {csv_path}")
    print(f"  Parcels with portfolio (>=2 APNs): {stats['parcels_with_portfolio']}")
    print(f"  Solo parcels:                       {stats['solo_parcels']}")
    print(f"  No owner (skipped):                 {stats['no_owner']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--county", default="butte")
    args = parser.parse_args()
    merge(args.csv_path, args.county)
