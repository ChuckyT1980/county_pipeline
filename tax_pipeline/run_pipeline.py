"""
Full pipeline runner — Stage 1 discovery -> Stage 2+3 verify/export.

Usage:
    python run_pipeline.py tehama
    python run_pipeline.py tehama --discovery-csv existing_file.csv  (skip Stage 1)
"""

import asyncio
import sys
import os
from datetime import datetime

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("county",
                        help="County slug from config.py (e.g. tehama)")
    parser.add_argument("--discovery-csv", default=None,
                        help="Skip Stage 1 and use an existing discovery CSV")
    parser.add_argument("--year", default="2025",
                        help="Tax year override (default: 2025)")
    args = parser.parse_args()

    county = args.county
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n{'='*50}")
    print(f"  TAX VERIFICATION PIPELINE")
    print(f"  County : {county.upper()}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    # ── Stage 1: Discovery (unless a CSV was passed in)
    if args.discovery_csv:
        discovery_csv = args.discovery_csv
        print(f"[Stage 1] Skipped — using existing: {discovery_csv}\n")
    else:
        from stage1_discover import discover
        discovery_csv = f"{county}_discovery_{ts}.csv"
        discover(county, discovery_csv)
        print()

    # ── Stage 2 + 3: Verify + Export
    from stage2_verify import verify
    audit_csv, crm_csv = verify(county, discovery_csv)

    print(f"\n{'='*50}")
    print(f"  PIPELINE COMPLETE")
    print(f"  Discovery : {discovery_csv}")
    print(f"  Audit     : {audit_csv}")
    print(f"  CRM       : {crm_csv}")
    print(f"  Finished  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
