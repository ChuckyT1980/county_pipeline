"""
Excess Proceeds Finder & Escheat Deadline Prioritizer
Processes historical auction sold data to identify surplus funds owed to former owners.
Calculates 1-year escheat deadline from deed recording date.

Outputs:
  excess_proceeds/excess_proceeds_COUNTY_YYYY.csv
  excess_proceeds/outreach_list_COUNTY_YYYY.csv (sorted by excess amount descending)

INTEGRITY RULE: this script REFUSES to fabricate results. It only processes
inputs that contain real sale data (min_bid + a price column or deed date).
A master parcel index (APN + address only) is NOT sale data — running one
through here produced 40,059 identical placeholder rows that would be
fraudulent to mail. Do not add default-value fallbacks back.
"""
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

EXCESS_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(EXCESS_DIR)

SALE_PRICE_COLS = ["sold_price", "winning_bid_amount", "sales_price"]
DEED_DATE_COLS = ["deed_date", "deed_recorded_date", "auction_date"]


def parse_date(d_str):
    if not d_str or pd.isna(d_str):
        return None
    d_str = str(d_str).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(d_str, fmt)
        except ValueError:
            pass
    return None


def _has_real_sale_columns(df: pd.DataFrame) -> bool:
    """True only if the frame actually carries sale data. A master parcel
    index (just APN + address, or rows where every sale field is a constant
    default) must return False."""
    if "min_bid" not in df.columns:
        return False
    has_price = any(c in df.columns for c in SALE_PRICE_COLS)
    has_deed = any(c in df.columns and df[c].notna().any() for c in DEED_DATE_COLS)
    if not (has_price or has_deed):
        return False
    # Guard against constant-default columns that "look" real but are filler.
    if any(c in df.columns for c in SALE_PRICE_COLS):
        price_col = next(c for c in SALE_PRICE_COLS if c in df.columns)
        uniq = df[price_col].dropna().nunique()
        if uniq <= 1 and len(df) > 10:
            return False
    return True


def process_excess_proceeds(county, year, df_sold, out_prefix):
    print(f"\n=== Processing Excess Proceeds: {county} ({year}) ===")

    if not _has_real_sale_columns(df_sold):
        print(f"  SKIPPED {county}: input has no real sale data "
              f"(columns={list(df_sold.columns)}). Not fabricating rows.")
        return None, None

    today = datetime.now()
    results = []
    estimates = 0

    for idx, row in df_sold.iterrows():
        apn = str(row.get("apn", "")).strip()
        min_bid = float(row.get("min_bid", 0) or 0)

        # Real sold price if present; otherwise this row is an estimate-only entry.
        sold_price = None
        for c in SALE_PRICE_COLS:
            if c in df_sold.columns and pd.notna(row.get(c)):
                sold_price = float(row[c])
                break
        sold_price_is_estimate = sold_price is None
        if sold_price is None:
            estimates += 1
            continue  # never invent a sale price

        excess_amount = sold_price - min_bid
        if excess_amount <= 0:
            continue

        deed_dt = None
        for c in DEED_DATE_COLS:
            if c in df_sold.columns:
                deed_dt = parse_date(row.get(c))
                if deed_dt:
                    break
        deed_is_estimate = deed_dt is None
        if deed_dt is None:
            # No deed date known — can't compute an escheat deadline. Record the
            # excess but flag it rather than guessing a date.
            escheat_deadline = None
            days_until_escheat = None
            priority = "DEED DATE UNKNOWN"
        else:
            escheat_deadline = deed_dt + timedelta(days=365)
            days_until_escheat = (escheat_deadline - today).days
            if days_until_escheat < 0:
                priority = "EXPIRED / ESCHEATED"
            elif days_until_escheat <= 60:
                priority = "HIGH (URGENT)"
            elif days_until_escheat <= 180:
                priority = "MEDIUM"
            else:
                priority = "LOW"

        owner_name = row.get("owner_name") or row.get("verified_current_owner_name") or ""
        mailing_addr = row.get("mailing_address") or ""
        situs_addr = row.get("situs_address") or ""

        results.append({
            "apn": str(apn),
            "county": county,
            "auction_year": str(deed_dt.year) if deed_dt else year,
            "deed_recorded_date": deed_dt.strftime("%Y-%m-%d") if deed_dt else "",
            "escheat_deadline": escheat_deadline.strftime("%Y-%m-%d") if escheat_deadline else "",
            "days_until_escheat": days_until_escheat,
            "min_bid": min_bid,
            "sold_price": sold_price,
            "excess_amount": round(excess_amount, 2),
            "priority_flag": priority,
            "former_owner_name": owner_name,
            "former_owner_mailing": mailing_addr,
            "property_situs": situs_addr,
        })

    df_res = pd.DataFrame(results)
    if df_res.empty:
        print(f"No excess proceeds found for {county} {year}.")
        return None, None

    df_res = df_res.sort_values(by="excess_amount", ascending=False)

    full_csv = os.path.join(EXCESS_DIR, f"excess_proceeds_{out_prefix}.csv")
    df_res.to_csv(full_csv, index=False)

    df_outreach = df_res[df_res["days_until_escheat"].notna() & (df_res["days_until_escheat"] >= -30)].copy()
    df_outreach = df_outreach.sort_values(by="excess_amount", ascending=False)
    outreach_csv = os.path.join(EXCESS_DIR, f"outreach_list_{out_prefix}.csv")
    df_outreach.to_csv(outreach_csv, index=False)

    total_excess = df_res["excess_amount"].sum()
    high_count = len(df_res[df_res["priority_flag"].str.contains("HIGH")])
    unknown_deed = len(df_res[df_res["priority_flag"] == "DEED DATE UNKNOWN"])

    print(f"  Processed {len(df_res)} surplus parcels.")
    print(f"  Total Excess Proceeds Identified: ${total_excess:,.2f}")
    print(f"  HIGH Priority (<=60 days to escheat): {high_count} parcels")
    print(f"  DEED DATE UNKNOWN (excess found, deadline not computable): {unknown_deed}")
    print(f"  Saved full dataset: {full_csv}")
    print(f"  Saved outreach list: {outreach_csv}")

    return full_csv, outreach_csv


def main():
    print("=== Excess Proceeds Finder & Escheat Deadline Prioritizer ===")

    # 1. Butte — real auction history (sold parcels only).
    butte_all_csv = os.path.join(PIPELINE_DIR, "tax_pipeline", "butte_all_auction_parcels.csv")
    if os.path.exists(butte_all_csv):
        df_b = pd.read_csv(butte_all_csv)
        if "status" in df_b.columns:
            df_b_sold = df_b[df_b["status"].astype(str).str.upper() == "SOLD"].copy()
            # Use each row's own auction year; fall back to a passed year only if absent.
            year = str(df_b_sold["year"].max()) if "year" in df_b_sold.columns else "2026"
            process_excess_proceeds("Butte", year, df_b_sold, "butte_2026")
        else:
            print("  SKIPPED Butte: no 'status' column — cannot tell what sold.")
    else:
        print(f"  SKIPPED Butte: no auction history at {butte_all_csv}")

    # 2. Fresno — REAL historical auction results parsed from the county's
    #    published "Report of Properties Sold" PDFs. The parser
    #    (fresno/fresno_fetch_and_parse_results.py) writes real APN + sales
    #    price + excess proceeds + min bid per row. Auction date is used as the
    #    deed-date proxy; deed recording typically follows the auction by a few
    #    months, so escheat deadlines computed here are conservative (earlier
    #    than actual) — safe for prioritization.
    fresno_csv = os.path.join(PIPELINE_DIR, "fresno", "fresno_historical_sales.csv")
    if os.path.exists(fresno_csv):
        df_f = pd.read_csv(fresno_csv, dtype=str)
        year = str(df_f["auction_date"].dropna().str[:4].max()) if "auction_date" in df_f.columns else "2025"
        process_excess_proceeds("Fresno", year, df_f, "fresno_2025")
    else:
        print(f"  SKIPPED Fresno: no historical sales at {fresno_csv}")
        print("  Run: python fresno/fresno_fetch_and_parse_results.py")

    # 3. Tehama — requires REAL auction-sold data. None currently exists in the
    #    repo (the authoritative master index is APN+address only, NOT sales).
    #    Do not fabricate. If a real sales CSV is later added, wire it up here.
    tehama_sales_candidates = [
        os.path.join(PIPELINE_DIR, "tehama", "tehama_auction_sold.csv"),
        os.path.join(EXCESS_DIR, "tehama_sold_input.csv"),
    ]
    tehama_sales_csv = next((p for p in tehama_sales_candidates if os.path.exists(p)), None)
    if tehama_sales_csv:
        df_t = pd.read_csv(tehama_sales_csv)
        year = "2025"
        if "year" in df_t.columns and df_t["year"].notna().any():
            year = str(int(df_t["year"].max()))
        process_excess_proceeds("Tehama", year, df_t, "tehama_2025")
    else:
        print("  SKIPPED Tehama: no real auction-sold data on disk.")
        print("  Required input columns: apn, min_bid, sold_price or winning_bid_amount, deed_date (and owner/mailing if available).")


if __name__ == "__main__":
    main()
