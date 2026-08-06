"""
Full pipeline runner — Stage 1 through Stage 8 (excluding PDF stages 5/6).

Usage:
    python run_pipeline_full.py tehama
    python run_pipeline_full.py tehama --discovery-csv existing_file.csv  (skip Stage 1)
    python run_pipeline_full.py tehama --start-stage 4 --crm-csv tehama_crm_20260719.csv
"""

import argparse
import sys
import os
import glob
from datetime import datetime


def banner(msg):
    print(f"\n{'='*55}")
    print(f"  {msg}")
    print(f"{'='*55}\n")


def find_latest(pattern):
    """Return the most recently modified file matching glob pattern, or None."""
    files = glob.glob(pattern)
    return max(files, key=os.path.getmtime) if files else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("county", help="County slug (e.g. tehama, shasta, butte, lassen)")
    parser.add_argument("--discovery-csv", default=None,
                        help="Skip Stage 1 — use existing discovery CSV")
    parser.add_argument("--crm-csv", default=None,
                        help="Skip Stages 1-3 — use existing CRM CSV for Stage 4+")
    parser.add_argument("--start-stage", type=int, default=1,
                        help="Start from this stage number (1, 2, 4, 7, or 8)")
    args = parser.parse_args()

    county = args.county.lower()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    banner(f"FULL TAX PIPELINE — {county.upper()} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Stage 1: Discovery ───────────────────────────────────────────────────
    if args.start_stage <= 1:
        if args.discovery_csv:
            discovery_csv = args.discovery_csv
            print(f"[Stage 1] Skipped — using: {discovery_csv}")
        else:
            from stage1_discover import discover
            discovery_csv = f"{county}_discovery_{ts}.csv"
            banner(f"Stage 1 — Parcel Discovery")
            discover(county, discovery_csv)
    else:
        discovery_csv = args.discovery_csv or find_latest(f"{county}_discovery_*.csv")
        if not discovery_csv:
            print(f"ERROR: --start-stage {args.start_stage} requires a discovery CSV. "
                  f"Pass --discovery-csv or run from Stage 1.")
            sys.exit(1)
        print(f"[Stage 1] Skipped — using: {discovery_csv}")

    # ── Stages 2 + 3: Verify + Export ───────────────────────────────────────
    if args.start_stage <= 2:
        banner("Stage 2/3 — Live Verification + Export")
        try:
            from stage2_verify import verify
        except ImportError:
            from tax_pipeline.stage2_verify import verify
        audit_csv, crm_csv = verify(county, discovery_csv)
        print(f"  Audit CSV : {audit_csv}")
        print(f"  CRM CSV   : {crm_csv}")
    else:
        crm_csv = args.crm_csv or find_latest(f"{county}_crm_*.csv")
        if not crm_csv:
            print(f"ERROR: No CRM CSV found. Pass --crm-csv or run from Stage 2.")
            sys.exit(1)
        print(f"[Stage 2/3] Skipped — using: {crm_csv}")

    # ── Stage 4: Owner Enrichment ────────────────────────────────────────────
    if args.start_stage <= 4:
        banner("Stage 4 — Owner Enrichment")
        from stage4_owner_enrich import main as stage4_main
        stage4_main(crm_csv)
        enriched_csv = crm_csv.replace(".csv", "_enriched.csv")
        print(f"  Enriched CSV: {enriched_csv}")
    else:
        print("[Stage 4] Skipped.")

    # ── Stage 7: Recorder Enrichment (Playwright) ────────────────────────────
    if args.start_stage <= 7:
        banner("Stage 7 — Recorder Enrichment (EagleWeb)")
        from stage7_recorder_enrich import scrape_liens
        scrape_liens(county)
    else:
        print("[Stage 7] Skipped.")

    # ── Stage 8: Skip Trace ──────────────────────────────────────────────────
    if args.start_stage <= 8:
        banner("Stage 8 — Skip Trace (Phone Lookup)")
        from stage8_skip_trace import run_skip_trace
        run_skip_trace(county)
    else:
        print("[Stage 8] Skipped.")

    banner(f"PIPELINE COMPLETE — {county.upper()} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
