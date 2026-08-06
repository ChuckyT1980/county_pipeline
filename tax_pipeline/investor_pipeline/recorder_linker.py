"""Join auction parcels with recorder tax-deed records by county + APN + time window.

Expected recorder CSV columns:
    county, apn, recording_date, document_number, document_type, grantee_raw, grantor_raw

The linker filters to deed-type documents recorded within 0-90 days after the auction date,
then joins on county + normalized APN.  One auction parcel can match multiple recorder
events (e.g. multiple docs recorded around the same date); the primary deed is the one
closest to the auction date.

Usage:
    from investor_pipeline.recorder_linker import link_auction_recorder

    joined = link_auction_recorder(auction_df, recorder_df)
"""

import pandas as pd
import numpy as np
from typing import Optional

from .apn_utils import normalize_apn

# Document types that indicate a tax-deed transfer from county to buyer
TAX_DEED_TYPES = {
    "TRUSTEE'S DEED", "TRUSTEE DEED", "TRUSTEES DEED",
    "DEED", "GRANT DEED", "QUITCLAIM DEED",
    "TAX DEED", "TAX SALE DEED",
}

# Time window: recording must be within this many days AFTER the auction date
DEFAULT_WINDOW_DAYS = (0, 90)


def load_recorder_csv(path: str, county: Optional[str] = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty:
        return df

    cols = list(df.columns)
    col_lower = [c.strip().lower() for c in cols]

    # Flexible column mapping
    def pick(names):
        for n in names:
            for i, cl in enumerate(col_lower):
                if cl == n.lower() or cl.endswith("/" + n.lower()):
                    return cols[i]
        return None

    result = pd.DataFrame()

    county_col = pick(["county"])
    if county_col:
        result["county"] = df[county_col].astype(str).str.strip()
    elif county:
        result["county"] = county
    else:
        result["county"] = ""

    apn_col = pick(["apn", "parcel_number", "parcel number", "property_id"])
    if apn_col:
        result["apn"] = df[apn_col].astype(str).apply(normalize_apn)
    else:
        result["apn"] = ""

    rec_date_col = pick(["recording_date", "recorded_date", "rec date", "date"])
    if rec_date_col:
        result["recording_date"] = pd.to_datetime(df[rec_date_col], errors="coerce")
    else:
        result["recording_date"] = pd.NaT

    doc_num_col = pick(["document_number", "doc_number", "doc_no", "document number", "doc num"])
    if doc_num_col:
        result["document_number"] = df[doc_num_col].astype(str).str.strip()
    else:
        result["document_number"] = ""

    doc_type_col = pick(["document_type", "doc_type", "document type", "doc type", "type"])
    if doc_type_col:
        result["document_type"] = df[doc_type_col].astype(str).str.strip().str.upper()
    else:
        result["document_type"] = ""

    grantee_col = pick(["grantee_raw", "grantee", "grantee name"])
    if grantee_col:
        result["grantee_raw"] = df[grantee_col].astype(str).str.strip()
    else:
        result["grantee_raw"] = ""

    grantor_col = pick(["grantor_raw", "grantor", "grantor name", "grantor(s)"])
    if grantor_col:
        result["grantor_raw"] = df[grantor_col].astype(str).str.strip()
    else:
        result["grantor_raw"] = ""

    return result


def filter_tax_deeds(recorder_df: pd.DataFrame,
                     deed_types: Optional[set] = None) -> pd.DataFrame:
    if deed_types is None:
        deed_types = TAX_DEED_TYPES
    if recorder_df.empty or "document_type" not in recorder_df.columns:
        return recorder_df
    mask = recorder_df["document_type"].isin(deed_types)
    return recorder_df[mask].copy()


def link_auction_recorder(auction_df: pd.DataFrame,
                          recorder_df: pd.DataFrame,
                          window_days: tuple = DEFAULT_WINDOW_DAYS) -> pd.DataFrame:
    """
    Join sold auction parcels to recorder deeds on county + apn + time window.

    Returns a DataFrame with one row per matched (auction_parcel, recorder_deed) pair.
    Columns are prefixed: 'auction_' for auction fields, 'recorder_' for recorder fields.
    """
    if auction_df.empty or recorder_df.empty:
        return pd.DataFrame()

    # Only consider sold auction parcels
    sold = auction_df[auction_df["sold_flag"]].copy()
    if sold.empty:
        return pd.DataFrame()

    # Ensure normalized APNs
    if "apn" in sold.columns:
        sold["apn"] = sold["apn"].astype(str).apply(normalize_apn)
    if "apn" in recorder_df.columns:
        rec = recorder_df.copy()
        rec["apn"] = rec["apn"].astype(str).apply(normalize_apn)
    else:
        rec = recorder_df.copy()

    # Filter to tax-deed types
    rec = filter_tax_deeds(rec)
    if rec.empty:
        return pd.DataFrame()

    # Merge on county + apn
    merged = pd.merge(
        sold, rec,
        on=["county", "apn"],
        how="inner",
        suffixes=("_auction", "_recorder"),
    )

    if merged.empty:
        return pd.DataFrame()

    # Filter by time window: recording_date within window_days after auction_date
    day_min, day_max = window_days
    delta = (merged["recording_date"] - merged["auction_date"]).dt.days
    merged = merged[delta.between(day_min, day_max, inclusive="both")].copy()

    if merged.empty:
        return pd.DataFrame()

    # Prefer the earliest recording per (county, apn, auction_id) as the primary deed
    merged["_rank"] = merged.groupby(["county", "apn", "auction_id"])["recording_date"].rank(
        method="dense", ascending=True
    )
    merged = merged[merged["_rank"] == 1].drop(columns="_rank")

    # Build output with clean column names
    result = pd.DataFrame()
    result["county"] = merged["county"]
    result["apn"] = merged["apn"]
    result["auction_id"] = merged["auction_id"]
    result["auction_date"] = merged["auction_date"]
    result["winning_bid_amount"] = merged.get("winning_bid_amount", float("nan"))
    result["recording_date"] = merged["recording_date"]
    result["document_number"] = merged["document_number"]
    result["document_type"] = merged.get("document_type_recorder", "")
    result["grantee_raw"] = merged.get("grantee_raw", "")
    result["grantor_raw"] = merged.get("grantor_raw", "")

    return result
