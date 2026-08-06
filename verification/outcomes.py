"""
Layer 5: post-auction outcome tracking + score calibration.

Two purposes:
1) After each auction cycle, ingest what actually happened per parcel
   (sold/redeemed/unsold/withdrawn + buyer + sale price) into
   auction_outcomes. Feeds the graph and next cycle's targeting.
2) Compare predicted priority_score vs. actual outcome across a cohort
   and emit a calibration delta so the scoring function can be tuned
   from evidence, not intuition.

Ingest source: a CSV or dict list with columns:
    apn, outcome_class, sale_price, buyer_name, trustees_deed_number,
    trustees_deed_date, auction_label, auction_date

Can be populated by:
- Running butte_buyer_tracker.py against historical PDFs (existing code)
- Manual entry from a post-auction report
- Future: automated post-auction Trustee's Deed extraction (new stage)
"""
import json
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from .db import connect
from .graph import canonical_name, _upsert_node, _upsert_edge


VALID_OUTCOMES = {"SOLD", "REDEEMED", "UNSOLD", "WITHDRAWN"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ingest_outcome(
    apn: str,
    county: str,
    auction_label: str,
    outcome_class: str,
    auction_date: str | None = None,
    sale_price: float | None = None,
    buyer_name: str | None = None,
    trustees_deed_number: str | None = None,
    trustees_deed_date: str | None = None,
    predicted_priority_score: float | None = None,
) -> int:
    """Record one parcel outcome. Also updates the graph if buyer is known."""
    assert outcome_class in VALID_OUTCOMES, f"outcome_class must be one of {VALID_OUTCOMES}"

    buyer_canonical = canonical_name(buyer_name) if buyer_name else None
    conn = connect()

    cur = conn.execute(
        """
        INSERT INTO auction_outcomes
            (apn, county, auction_label, auction_date, outcome_class, sale_price,
             buyer_name, buyer_canonical_name, trustees_deed_number, trustees_deed_date,
             predicted_priority_score, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (apn, county, auction_label, auction_date, outcome_class, sale_price,
         buyer_name, buyer_canonical, trustees_deed_number, trustees_deed_date,
         predicted_priority_score, _now()),
    )
    outcome_id = cur.lastrowid

    # If we know the buyer, add them to the graph as a grantee on this parcel via the trustees deed
    if buyer_canonical and outcome_class == "SOLD":
        from .graph import entity_kind
        parcel_id = _upsert_node(conn, "parcel", apn=apn, county=county, display=apn)
        kind = entity_kind(buyer_canonical)
        buyer_id = _upsert_node(conn, kind, canonical=buyer_canonical, display=buyer_name)
        if trustees_deed_number:
            doc_id = _upsert_node(conn, "doc", doc_number=trustees_deed_number, county=county,
                                   display=f"TRUSTEES DEED {trustees_deed_number}",
                                   extra={"doc_type": "TRUSTEES_DEED_UPON_SALE",
                                          "recording_date": trustees_deed_date,
                                          "sale_price": sale_price})
            _upsert_edge(conn, buyer_id, doc_id, "grantee", doc_id=doc_id)
            _upsert_edge(conn, doc_id, parcel_id, "affects", doc_id=doc_id)

    conn.commit()
    conn.close()
    return outcome_id


def ingest_from_csv(csv_path: str, county: str) -> dict:
    """Bulk-ingest outcomes from a CSV. Required columns: apn, outcome_class.
    Optional: auction_label, auction_date, sale_price, buyer_name,
    trustees_deed_number, trustees_deed_date, predicted_priority_score."""
    df = pd.read_csv(csv_path, dtype=str)
    if "apn" not in df.columns or "outcome_class" not in df.columns:
        raise ValueError("CSV must have at least apn and outcome_class columns")

    stats = {"ingested": 0, "invalid_outcome": 0, "with_buyer": 0}
    for _, row in df.iterrows():
        outcome = str(row.get("outcome_class", "")).strip().upper()
        if outcome not in VALID_OUTCOMES:
            stats["invalid_outcome"] += 1
            continue
        buyer = str(row.get("buyer_name", "")).strip() or None
        try:
            sale_price = float(str(row.get("sale_price", "")).replace("$", "").replace(",", "")) if row.get("sale_price") else None
        except (ValueError, TypeError):
            sale_price = None
        try:
            predicted = float(row.get("predicted_priority_score")) if row.get("predicted_priority_score") else None
        except (ValueError, TypeError):
            predicted = None

        ingest_outcome(
            apn=row["apn"],
            county=county,
            auction_label=row.get("auction_label", "unknown"),
            outcome_class=outcome,
            auction_date=row.get("auction_date"),
            sale_price=sale_price,
            buyer_name=buyer,
            trustees_deed_number=row.get("trustees_deed_number"),
            trustees_deed_date=row.get("trustees_deed_date"),
            predicted_priority_score=predicted,
        )
        stats["ingested"] += 1
        if buyer:
            stats["with_buyer"] += 1
    return stats


def calibrate_scoring(county: str, auction_label: str | None = None) -> dict:
    """
    Compare predicted priority scores against actual outcomes to detect
    whether the scoring is well-calibrated.

    Returns a dict with correlation between score and outcome, mean score
    for sold vs unsold, and a recommended calibration delta. Writes a row
    to score_calibration for the audit trail.
    """
    conn = connect()
    where = "county = ?"
    params: list = [county]
    if auction_label:
        where += " AND auction_label = ?"
        params.append(auction_label)

    rows = conn.execute(
        f"""
        SELECT outcome_class, sale_price, predicted_priority_score
          FROM auction_outcomes
         WHERE {where} AND predicted_priority_score IS NOT NULL
        """,
        params,
    ).fetchall()

    n = len(rows)
    if n < 5:
        return {"error": f"need at least 5 outcomes with predictions, have {n}"}

    sold_scores = [r["predicted_priority_score"] for r in rows if r["outcome_class"] == "SOLD"]
    other_scores = [r["predicted_priority_score"] for r in rows if r["outcome_class"] != "SOLD"]

    if not sold_scores or not other_scores:
        return {"error": "need both SOLD and non-SOLD outcomes for calibration"}

    mean_sold = sum(sold_scores) / len(sold_scores)
    mean_other = sum(other_scores) / len(other_scores)
    lift = mean_sold - mean_other

    # If sold parcels averaged 5+ points higher than others, our scoring
    # was well-calibrated. If lift is near zero or negative, scoring is broken.
    result = {
        "n_outcomes": n,
        "n_sold": len(sold_scores),
        "n_other": len(other_scores),
        "mean_score_sold": round(mean_sold, 2),
        "mean_score_other": round(mean_other, 2),
        "lift": round(lift, 2),
        "verdict": "well_calibrated" if lift >= 5 else "poor_calibration" if lift < 0 else "weak_signal",
    }

    conn.execute(
        """
        INSERT INTO score_calibration
            (calibrated_at, county, sample_size, formula_before, formula_after,
             r_squared_before, r_squared_after, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (_now(), county, n, "log-scaled balance (v0)", "log-scaled balance (v0)",
         None, None, json.dumps(result)),
    )
    conn.commit()
    conn.close()
    return result


def outcomes_summary(county: str, auction_label: str | None = None) -> dict:
    conn = connect()
    where = "county = ?"
    params: list = [county]
    if auction_label:
        where += " AND auction_label = ?"
        params.append(auction_label)
    rows = conn.execute(
        f"""
        SELECT outcome_class, COUNT(*) AS n, AVG(sale_price) AS avg_sale, SUM(sale_price) AS total_sale
          FROM auction_outcomes
         WHERE {where}
         GROUP BY outcome_class
        """,
        params,
    ).fetchall()
    conn.close()
    return {r["outcome_class"]: dict(r) for r in rows}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    ingest_p = sub.add_parser("ingest", help="Bulk ingest outcomes from CSV")
    ingest_p.add_argument("csv_path")
    ingest_p.add_argument("--county", default="butte")

    calib_p = sub.add_parser("calibrate", help="Compare predicted score vs outcomes")
    calib_p.add_argument("--county", default="butte")
    calib_p.add_argument("--auction-label", default=None)

    sum_p = sub.add_parser("summary", help="Outcome summary for a county")
    sum_p.add_argument("--county", default="butte")
    sum_p.add_argument("--auction-label", default=None)

    args = parser.parse_args()
    if args.cmd == "ingest":
        stats = ingest_from_csv(args.csv_path, args.county)
        print("Ingest complete:", stats)
    elif args.cmd == "calibrate":
        result = calibrate_scoring(args.county, args.auction_label)
        print(json.dumps(result, indent=2))
    elif args.cmd == "summary":
        print(json.dumps(outcomes_summary(args.county, args.auction_label), indent=2, default=str))
