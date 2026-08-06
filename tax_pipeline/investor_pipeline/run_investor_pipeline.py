#!/usr/bin/env python3
"""Top-level runner for the investor / frequent-buyer pipeline.

Usage:
    # Single county
    python run_investor_pipeline.py --auction-csv butte_2026_sold.csv \\
                                    --recorder-csv butte_recorder_tax_deeds.csv \\
                                    --county Butte

    # Multiple counties (auto-detect county from filename)
    python run_investor_pipeline.py --auction-csvs butte_2026.csv tehama_2025.csv \\
                                    --recorder-csvs butte_deeds.csv tehama_deeds.csv

    # Specify output directory
    python run_investor_pipeline.py ... --output-dir ./investor_output
"""

import argparse
import sys
from pathlib import Path

# Ensure parent is on path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from investor_pipeline.bid4assets_extractor import load_auction_csv, load_auction_csvs
from investor_pipeline.recorder_linker import load_recorder_csv, link_auction_recorder
from investor_pipeline.investor_aggregator import build_investor_tables, query_top_buyers


def parse_args():
    parser = argparse.ArgumentParser(
        description="Tax-deed investor / frequent-buyer pipeline"
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--auction-csv", help="Single Bid4Assets auction CSV"
    )
    input_group.add_argument(
        "--auction-csvs", nargs="+", help="Multiple auction CSVs"
    )

    parser.add_argument(
        "--recorder-csv", help="Single recorder deed CSV"
    )
    parser.add_argument(
        "--recorder-csvs", nargs="+", help="Multiple recorder CSVs (one per county)"
    )
    parser.add_argument(
        "--county", default=None, help="County name (for single-county runs)"
    )
    parser.add_argument(
        "--output-dir", default="investor_output", help="Output directory"
    )
    parser.add_argument(
        "--no-save", action="store_true", help="Skip CSV output (return DataFrames only)"
    )
    parser.add_argument(
        "--window-days", type=int, default=90,
        help="Max days after auction to match recorder deed (default 90)"
    )
    parser.add_argument(
        "--county-map", nargs="+", metavar="KEYWORD=COUNTY",
        help="Map filename keywords to county names, e.g. butte=Butte tehama=Tehama"
    )
    return parser.parse_args()


def build_county_map(args) -> dict:
    mapping = {}
    if args.county_map:
        for kv in args.county_map:
            if "=" in kv:
                k, v = kv.split("=", 1)
                mapping[k.lower()] = v
    # Auto-map from --county
    if args.county:
        mapping[args.county.lower()] = args.county
    return mapping


def main():
    args = parse_args()
    county_map = build_county_map(args)
    output_dir = args.output_dir
    window = (0, args.window_days)

    # ── 1. Load auction data ─────────────────────────────────────────────
    print("=" * 60)
    print("INVESTOR PIPELINE — Tax-Deed Buyer Intelligence")
    print("=" * 60)

    if args.auction_csv:
        print(f"\n[1/4] Loading auction CSV: {args.auction_csv}")
        auction_df = load_auction_csv(args.auction_csv, county=args.county)
    else:
        print(f"\n[1/4] Loading {len(args.auction_csvs)} auction CSVs...")
        auction_df = load_auction_csvs(args.auction_csvs, county_map=county_map)

    if auction_df.empty:
        print("  No auction data loaded. Exiting.")
        return

    sold_count = auction_df["sold_flag"].sum()
    print(f"  {len(auction_df)} parcels loaded, {sold_count} sold")

    # ── 2. Load recorder data ────────────────────────────────────────────
    print(f"\n[2/4] Loading recorder deed CSVs...")
    recorder_frames = []

    if args.recorder_csv:
        recorder_frames.append(
            load_recorder_csv(args.recorder_csv, county=args.county)
        )
    elif args.recorder_csvs:
        for path in args.recorder_csvs:
            county = None
            for key, val in county_map.items():
                if key in path.lower():
                    county = val
                    break
            recorder_frames.append(load_recorder_csv(path, county=county))

    if not recorder_frames:
        print("  ERROR: No recorder CSV(s) provided.")
        print("  Provide --recorder-csv or --recorder-csvs.")
        return

    import pandas as pd
    recorder_df = pd.concat(recorder_frames, ignore_index=True) if len(recorder_frames) > 1 else recorder_frames[0]
    print(f"  {len(recorder_df)} recorder deed records loaded")

    # ── 3. Link auction + recorder ───────────────────────────────────────
    print(f"\n[3/4] Linking auction parcels to recorder deeds (window: 0–{args.window_days} days)...")
    linked = link_auction_recorder(auction_df, recorder_df, window_days=window)
    print(f"  {len(linked)} purchase matches found")

    if linked.empty:
        print("  No matches — check county name consistency and time windows.")
        return

    # ── 4. Build investor tables ─────────────────────────────────────────
    print(f"\n[4/4] Aggregating investor / buyer tables...")
    investors, investor_deeds = build_investor_tables(
        linked,
        output_dir=output_dir,
        save_csv=not args.no_save,
    )

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n  {'=' * 50}")
    print(f"  SUMMARY")
    print(f"  {'=' * 50}")
    print(f"  Total unique investors/buyers:  {len(investors)}")
    print(f"  Total deed purchases tracked:    {len(investor_deeds)}")
    print(f"  Total capital deployed:       ${investors['total_capital_deployed'].sum():,.0f}")
    print()

    # Top 10
    top = investors.head(10)
    print(f"  {'Top 10 Buyers by Capital Deployed':^50}")
    print(f"  {'-' * 50}")
    for _, row in top.iterrows():
        print(f"  {row['entity_name_normalized'][:40]:40s}"
              f" ${row['total_capital_deployed']:>8,.0f}  "
              f"{row['total_deeds']:3d} deeds  {row['counties']}")

    print(f"\n  {'=' * 50}")
    print(f"  Done.  Output in: {output_dir}/")


if __name__ == "__main__":
    main()
