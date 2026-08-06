"""Aggregate linked auction-deed records into the investor and investor_deeds tables.

Assumes the input has already been through:
    1. bid4assets_extractor.load_auction_csv(s)
    2. recorder_linker.link_auction_recorder(auction_df, recorder_df)
    3. entity_normalize applied to grantee_raw

Outputs:
    investors.csv       — one row per normalized entity
    investor_deeds.csv  — one row per deed-level purchase
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional

from .entity_normalize import (
    normalize_entity,
    classify_entity_type,
    entity_id,
    pick_representative_name,
)


def build_investor_tables(
    linked_df: pd.DataFrame,
    output_dir: str = "output",
    save_csv: bool = True,
) -> tuple:
    """Build and return (investors_df, investor_deeds_df), optionally saving CSVs.

    Parameters
    ----------
    linked_df : DataFrame
        Must contain columns: county, apn, auction_id, auction_date,
        winning_bid_amount, recording_date, document_number, grantee_raw
    output_dir : str
        Directory for output CSVs.
    save_csv : bool
        If True, write investors.csv and investor_deeds.csv.

    Returns
    -------
    (investors_df, investor_deeds_df)
    """
    if linked_df.empty:
        empty = pd.DataFrame()
        if save_csv:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            empty.to_csv(Path(output_dir) / "investors.csv", index=False)
            empty.to_csv(Path(output_dir) / "investor_deeds.csv", index=False)
        return empty, empty

    df = linked_df.copy()

    # ── 1. Normalize entity names ────────────────────────────────────────
    df["entity_name_normalized"] = df["grantee_raw"].apply(normalize_entity)
    df["entity_type"] = df["entity_name_normalized"].apply(classify_entity_type)
    df["entity_id"] = df["entity_name_normalized"].apply(entity_id)

    # ── 2. Build investor_deeds detail table ─────────────────────────────
    deeds_cols = [
        "entity_id", "entity_name_normalized", "entity_type",
        "county", "apn", "auction_id", "auction_date",
        "winning_bid_amount", "recording_date", "document_number",
    ]
    available = [c for c in deeds_cols if c in df.columns]
    investor_deeds = df[available].copy()
    investor_deeds = investor_deeds.sort_values(["entity_id", "recording_date"]).reset_index(drop=True)

    # ── 3. Build investors aggregate table ───────────────────────────────
    def aggregate_group(grp: pd.DataFrame):
        raw_names = grp["grantee_raw"].tolist()
        return pd.Series({
            "entity_name_raw": pick_representative_name(raw_names),
            "entity_name_normalized": grp["entity_name_normalized"].iloc[0],
            "entity_type": grp["entity_type"].iloc[0],
            "total_deeds": len(grp),
            "total_capital_deployed": grp["winning_bid_amount"].sum(skipna=True),
            "first_purchase_date": grp["recording_date"].min(),
            "last_purchase_date": grp["recording_date"].max(),
            "counties": ";".join(sorted(grp["county"].unique())),
        })

    investors = df.groupby("entity_id", sort=False).apply(aggregate_group).reset_index()

    # ── 4. Scores ────────────────────────────────────────────────────────
    now = pd.Timestamp.today()
    cutoff_24m = now - pd.DateOffset(months=24)

    investors["recent_activity_score"] = 0.0
    investors["frequency_score"] = 0.0

    for idx, row in investors.iterrows():
        eid = row["entity_id"]
        entity_deeds = investor_deeds[investor_deeds["entity_id"] == eid]

        # Recent activity: deeds in last 24 months
        recent = entity_deeds[
            entity_deeds["recording_date"].notna()
            & (entity_deeds["recording_date"] >= cutoff_24m)
        ]
        investors.at[idx, "recent_activity_score"] = float(len(recent))

        # Frequency score: log2(1 + total_deeds) — smooth scaling
        investors.at[idx, "frequency_score"] = np.log2(1 + row["total_deeds"])

    investors = investors.sort_values("total_capital_deployed", ascending=False).reset_index(drop=True)

    # ── 5. Save ───────────────────────────────────────────────────────────
    if save_csv:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        investors.to_csv(out / "investors.csv", index=False)
        investor_deeds.to_csv(out / "investor_deeds.csv", index=False)
        print(f"  Wrote {out / 'investors.csv'} ({len(investors)} entities)")
        print(f"  Wrote {out / 'investor_deeds.csv'} ({len(investor_deeds)} deed records)")

    return investors, investor_deeds


def query_top_buyers(investors_df: pd.DataFrame,
                     counties: Optional[list] = None,
                     min_counties: int = 0,
                     min_capital: float = 0.0,
                     top_n: int = 20) -> pd.DataFrame:
    """Filter investors for common analytical queries.

    Parameters
    ----------
    counties : list, optional
        If given, filter to entities active in ANY of these counties.
    min_counties : int
        Minimum number of distinct counties (e.g. 3 for multi-county buyers).
    min_capital : float
        Minimum total capital deployed.
    top_n : int
        Return top N by total_capital_deployed.

    Returns
    -------
    DataFrame sorted by total_capital_deployed descending.
    """
    df = investors_df.copy()

    if counties:
        mask = df["counties"].apply(
            lambda c: any(co in str(c).split(";") for co in counties)
        )
        df = df[mask]

    if min_counties > 0:
        df = df[df["counties"].str.count(";") + 1 >= min_counties]

    if min_capital > 0.0:
        df = df[df["total_capital_deployed"] >= min_capital]

    return df.sort_values("total_capital_deployed", ascending=False).head(top_n)
