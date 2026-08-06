"""
Merges the latest verification-run provenance into a CRM-ready CSV.

For every row in the call sheet, adds sibling columns per field it
carries a value for:
    <field>_source      — where the value came from
    <field>_confidence  — 0..1 baseline confidence from the source

Also adds:
    verification_score          — completeness_score from parcel_verifications (0..100)
    verification_sources        — comma-separated succeeded sources
    verification_flag_count     — number of warn+error flags on this parcel this run
    verification_run_id         — for traceability

Idempotent: re-running against the same CSV updates the values in place.
"""
import argparse
import os
from pathlib import Path

import pandas as pd

from .db import connect


TRACKED_FIELDS = ("owner_name", "mailing_address", "situs_address", "flood_zone", "fire_hazard_zone")

# CSV column name -> verification field_name in field_provenance
CSV_TO_FIELD = {
    "verified_current_owner_name": "owner_name",
    "mailing_address": "mailing_address",
    "situs_address": "situs_address",
    "flood_zone": "flood_zone",
    "fire_hazard_zone": "fire_hazard_zone",
}


def latest_run_id(conn, county: str) -> int | None:
    """Latest completed run that actually recorded field_provenance
    (i.e. an address/enrichment run, not a downstream layer)."""
    row = conn.execute(
        """
        SELECT r.id FROM verification_runs r
         WHERE r.county = ? AND r.status = 'completed'
           AND EXISTS (SELECT 1 FROM field_provenance fp WHERE fp.run_id = r.id)
         ORDER BY r.started_at DESC LIMIT 1
        """,
        (county,),
    ).fetchone()
    return row["id"] if row else None


def load_provenance(conn, run_id: int) -> pd.DataFrame:
    """Latest provenance per (apn, field_name) across ALL completed runs for
    this county — not just the current run. Each field gets the freshest
    provenance record regardless of which run produced it."""
    rows = conn.execute(
        """
        SELECT fp.apn, fp.field_name, fp.source, fp.confidence
          FROM field_provenance fp
          JOIN (
              SELECT apn, field_name, MAX(id) AS max_id
                FROM field_provenance
               GROUP BY apn, field_name
          ) latest
            ON latest.max_id = fp.id
        """
    ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def load_parcel_scores(conn, run_id: int) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT pv.apn,
               pv.completeness_score,
               pv.sources_succeeded,
               (SELECT COUNT(*) FROM verification_flags vf
                 WHERE vf.run_id = pv.run_id AND vf.apn = pv.apn
                   AND vf.severity IN ('warn','error')) AS flag_count
          FROM parcel_verifications pv
         WHERE pv.run_id = ?
        """,
        (run_id,),
    ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def enrich_csv(csv_path: str, county: str = "butte") -> None:
    conn = connect()
    run_id = latest_run_id(conn, county)
    if run_id is None:
        print(f"No completed verification run for county={county}. Nothing to merge.")
        return

    prov = load_provenance(conn, run_id)
    scores = load_parcel_scores(conn, run_id)
    df = pd.read_csv(csv_path, dtype=str)

    # Ensure sibling columns exist
    for csv_col, field in CSV_TO_FIELD.items():
        for suffix in ("source", "confidence"):
            col = f"{field}_{suffix}"
            if col not in df.columns:
                df[col] = ""
    for meta in ("verification_score", "verification_sources", "verification_flag_count", "verification_run_id"):
        if meta not in df.columns:
            df[meta] = ""

    # Merge provenance per (apn, field)
    filled = {csv_col: 0 for csv_col in CSV_TO_FIELD}
    for _, prov_row in prov.iterrows():
        apn = prov_row["apn"]
        field = prov_row["field_name"]
        source = prov_row["source"]
        confidence = prov_row["confidence"]
        matching_rows = df[df["apn"] == apn].index
        for idx in matching_rows:
            for csv_col, mapped_field in CSV_TO_FIELD.items():
                if mapped_field == field:
                    df.at[idx, f"{field}_source"] = source
                    df.at[idx, f"{field}_confidence"] = f"{confidence:.2f}"
                    filled[csv_col] += 1

    # Merge per-parcel roll-ups
    for _, s_row in scores.iterrows():
        apn = s_row["apn"]
        matching_rows = df[df["apn"] == apn].index
        for idx in matching_rows:
            df.at[idx, "verification_score"] = f"{s_row['completeness_score']:.0f}" if s_row["completeness_score"] is not None else ""
            df.at[idx, "verification_sources"] = ",".join(
                sorted(set(s for s in (s_row["sources_succeeded"] or "").strip("[]").replace('"', '').split(",") if s.strip()))
            )
            df.at[idx, "verification_flag_count"] = str(s_row["flag_count"] or 0)
            df.at[idx, "verification_run_id"] = str(run_id)

    df.to_csv(csv_path, index=False)

    print(f"Merged verification run #{run_id} into {os.path.basename(csv_path)}")
    print(f"  rows in CSV:                    {len(df)}")
    print(f"  provenance records merged:      {sum(filled.values())}")
    for csv_col, n in filled.items():
        print(f"    {csv_col:35s}: {n}")
    vs = df["verification_score"]
    populated_mask = vs.notna() & (vs.astype(str).str.strip() != "") & (vs.astype(str).str.strip().str.lower() != "nan")
    print(f"  parcels with verification_score: {populated_mask.sum()} of {len(df)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv_path")
    p.add_argument("--county", default="butte")
    args = p.parse_args()
    enrich_csv(args.csv_path, args.county)
