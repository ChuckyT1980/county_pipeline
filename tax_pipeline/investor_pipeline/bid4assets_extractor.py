"""Load and normalize Bid4Assets auction CSVs into a standard dataframe.

Expected input CSV columns (mapped flexibly):
    county, auction_id, auction_date, apn, minimum_bid, winning_bid_amount, status

Derived fields:
    sold_flag    — bool, True if status == "SOLD"
    reoffer_flag — bool, True if status in ("REOFFER", "REOFFERED")

Usage:
    from investor_pipeline.bid4assets_extractor import load_auction_csv

    df = load_auction_csv("butte_2026_sold.csv", county="Butte")
    # or batch:
    df = load_auction_csvs(["butte_2026.csv", "tehama_2025.csv"])
"""

import pandas as pd
import re
from pathlib import Path
from typing import List, Optional

from .apn_utils import normalize_apn

_COLUMN_ALIASES = {
    "county": ["county", "county_name", "county name"],
    "auction_id": ["auction_id", "sale_id", "sale number", "id"],
    "auction_date": ["auction_date", "sale_date", "date", "auction date"],
    "apn": ["apn", "parcel_number", "parcel number", "property_id", "property id", "parcel"],
    "minimum_bid": ["minimum_bid", "min_bid", "min bid", "opening_bid", "opening bid", "starting_bid"],
    "winning_bid_amount": ["winning_bid_amount", "winning bid", "sale_amount", "sale amount",
                          "amount", "bid_amount", "bid amount", "final_bid", "high_bid"],
    "status": ["status", "result", "outcome", "sale_status", "disposition"],
}

_SOLD_KEYWORDS = {"SOLD", "SOLD*", "S", "PURCHASED", "AWARDED"}
_REOFFER_KEYWORDS = {"REOFFER", "REOFFERED", "RE-OFFERED", "REOFFER*", "R"}


def _find_column(candidates: List[str], cols: List[str]) -> Optional[str]:
    col_lower = [c.strip().lower() for c in cols]
    for alias in candidates:
        for i, cl in enumerate(col_lower):
            if cl == alias.lower():
                return cols[i]
    for alias in candidates:
        for i, cl in enumerate(col_lower):
            if cl.startswith(alias.lower()):
                return cols[i]
    return None


def load_auction_csv(path: str, county: Optional[str] = None) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Auction CSV not found: {path}")

    df = pd.read_csv(path)
    if df.empty:
        return df

    cols = list(df.columns)

    mapped = {}
    for target, aliases in _COLUMN_ALIASES.items():
        c = _find_column(aliases, cols)
        if c:
            mapped[target] = c

    result = pd.DataFrame()

    # county
    if "county" in mapped:
        result["county"] = df[mapped["county"]].astype(str).str.strip()
    elif county:
        result["county"] = county
    else:
        result["county"] = ""

    # auction_id
    if "auction_id" in mapped:
        result["auction_id"] = df[mapped["auction_id"]].astype(str).str.strip()
    else:
        result["auction_id"] = ""

    # auction_date
    if "auction_date" in mapped:
        result["auction_date"] = pd.to_datetime(df[mapped["auction_date"]], errors="coerce")
    else:
        result["auction_date"] = pd.NaT

    # apn
    if "apn" in mapped:
        result["apn"] = df[mapped["apn"]].astype(str).apply(normalize_apn)
    else:
        result["apn"] = ""

    # minimum_bid
    if "minimum_bid" in mapped:
        result["minimum_bid"] = (
            df[mapped["minimum_bid"]]
            .astype(str)
            .str.replace(r"[$,]", "", regex=True)
            .str.strip()
        )
        result["minimum_bid"] = pd.to_numeric(result["minimum_bid"], errors="coerce").fillna(0.0)
    else:
        result["minimum_bid"] = 0.0

    # winning_bid_amount
    if "winning_bid_amount" in mapped:
        result["winning_bid_amount"] = (
            df[mapped["winning_bid_amount"]]
            .astype(str)
            .str.replace(r"[$,]", "", regex=True)
            .str.strip()
        )
        result["winning_bid_amount"] = pd.to_numeric(result["winning_bid_amount"], errors="coerce")
    else:
        result["winning_bid_amount"] = float("nan")

    # status
    if "status" in mapped:
        result["status"] = df[mapped["status"]].astype(str).str.strip().str.upper()
    else:
        result["status"] = ""

    # Derived flags
    result["sold_flag"] = result["status"].isin(_SOLD_KEYWORDS)
    result["reoffer_flag"] = result["status"].isin(_REOFFER_KEYWORDS)

    return result


def load_auction_csvs(paths: List[str], county_map: Optional[dict] = None) -> pd.DataFrame:
    frames = []
    for p in paths:
        county = None
        if county_map:
            for key, val in county_map.items():
                if key in p.lower():
                    county = val
                    break
        df = load_auction_csv(p, county=county)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
