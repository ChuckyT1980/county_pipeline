"""
county_query_engine.py — Universal 58-County Intelligence Query Engine.

The single entry point for querying property intelligence and surplus recovery data
across all 58 California counties.

PREDICTIVE PRINCIPLE:
  We DO NOT wait for county tax collector auction lists.
  The engine continuously scans the Master Assessor Roll & Signal Scans (72K-441K parcels per county),
  scoring tax delinquency, lien signals, affidavit of death, and out-of-state owners
  to predict impending tax-defaulted opportunities 6-12 months BEFORE the county lists them.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from integrity_circuit_breaker import run_circuit_breaker_probe
from owner_resolve import resolve_owner
from predictive_scorer import score_excess_proceeds, score_property_intelligence
from report_builder import build_excess_proceeds_report, build_property_intelligence_dossier

ROOT = Path(__file__).resolve().parent
DATA_COUNTIES = ROOT / "data" / "counties"
DATA_ROOT = ROOT / "data"


def query_county_data(
    county_key: Optional[str] = None,
    apn: Optional[str] = None,
    lead_type: str = "all",
    out_of_state_only: bool = False,
    run_circuit_breaker: bool = True,
    generate_reports: bool = False,
    top_n: int = 50,
) -> dict[str, Any]:
    """Universal query function covering all 58 CA counties."""
    counties_to_query = []
    if county_key and county_key.lower() != "all":
        counties_to_query = [county_key.lower().strip()]
    else:
        found_dirs = set()
        if DATA_COUNTIES.exists():
            found_dirs.update([d.name for d in DATA_COUNTIES.iterdir() if d.is_dir() and not d.name.startswith("_")])
        if DATA_ROOT.exists():
            found_dirs.update([d.name for d in DATA_ROOT.iterdir() if d.is_dir() and not d.name.startswith("_") and d.name != "counties"])
        counties_to_query = sorted(list(found_dirs))
        if not counties_to_query:
            counties_to_query = ["humboldt", "tehama", "butte", "shasta", "fresno", "kern"]

    results = {
        "query_parameters": {
            "county": county_key or "all",
            "apn": apn,
            "lead_type": lead_type,
            "out_of_state_only": out_of_state_only,
        },
        "counties_searched": counties_to_query,
        "pre_auction_intel": [],
        "excess_proceeds": [],
        "reports_generated": [],
        "circuit_breaker_status": {},
    }

    for county in counties_to_query:
        if run_circuit_breaker:
            cb = run_circuit_breaker_probe(county, sample_size=5)
            results["circuit_breaker_status"][county] = cb["status"]
            if cb["status"] == "HALTED":
                print(f"[query_engine] Skipping county '{county}' due to circuit breaker HALT.", file=sys.stderr)
                continue

        # Look in both data/counties/{county}/ and data/{county}/
        candidate_dirs = [DATA_COUNTIES / county, DATA_ROOT / county]
        existing_dirs = [d for d in candidate_dirs if d.exists()]

        if not existing_dirs:
            continue

        # ── 1. Excess Proceeds Leg ───────────────────────────────────────────
        if lead_type in ("all", "excess", "excess_proceeds"):
            for c_dir in existing_dirs:
                ep_file = c_dir / "excess_proceeds.csv"
                tp_file = c_dir / "tax_deed_parcels.csv"
                target_csv = tp_file if tp_file.exists() else (ep_file if ep_file.exists() else None)

                if target_csv:
                    with target_csv.open("r", encoding="utf-8", errors="ignore") as fh:
                        reader = csv.DictReader(fh)
                        for row in reader:
                            row_apn = row.get("apn_dash") or row.get("apn") or ""
                            if apn and apn.replace("-", "") not in row_apn.replace("-", ""):
                                continue

                            owner = row.get("owner") or row.get("owner_of_record") or ""
                            out_of_state = "Y" in str(row.get("out_of_state", "")).upper() or (row.get("situs") and "no situs" in str(row.get("situs")).lower())

                            if out_of_state_only and not out_of_state:
                                continue

                            scores = score_excess_proceeds(row)
                            item = {
                                "county": county,
                                "apn": row_apn,
                                "owner": owner,
                                "excess_proceeds": scores["excess_amount_clean"],
                                "claim_deadline": row.get("claim_deadline") or "N/A",
                                "urgency_status": scores["urgency_status"],
                                "recoverability_score": scores["recoverability_score"],
                                "heir_locatability_tier": scores["heir_locatability_tier"],
                                "deed_status": row.get("deed_status") or "N/A",
                                "situs": row.get("situs") or "No Situs Address",
                                "raw_row": row,
                            }
                            results["excess_proceeds"].append(item)

                            if generate_reports:
                                rf = build_excess_proceeds_report(row, county)
                                results["reports_generated"].append(str(rf.resolve()))
                    break

        # ── 2. Pre-Auction Predictive Property Intelligence Leg ──────────────
        if lead_type in ("all", "prop_intel", "pre_auction"):
            target_intel = None
            for c_dir in existing_dirs:
                possible_files = [
                    c_dir / "pre_auction_intel.csv",
                    c_dir / f"{county}_signal_scan_full.csv",
                    c_dir / f"{county}_auction_candidates.csv",
                    c_dir / "predicted_auction.csv",
                    c_dir / "roll.csv",
                ]
                for pf in possible_files:
                    if pf.exists():
                        target_intel = pf
                        break
                if target_intel:
                    break

            if target_intel:
                scored_parcels = []
                with target_intel.open("r", encoding="utf-8", errors="ignore") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        row_apn = row.get("apn") or row.get("asmt") or row.get("APN") or ""
                        if apn and apn.replace("-", "") not in row_apn.replace("-", ""):
                            continue

                        scores = score_property_intelligence(row)
                        owner_val = (
                            row.get("verified_current_owner_name") or
                            row.get("owner_of_record") or
                            row.get("owner_name") or
                            row.get("assessee_name") or
                            row.get("Assessee") or
                            row.get("owner") or
                            row.get("name") or
                            "UNKNOWN"
                        )
                        if not owner_val or owner_val.strip().upper() in ("UNKNOWN", "NONE", "NULL", "NOT FOUND"):
                            res_owner = resolve_owner(row_apn, county, emit_dorks=False)
                            if res_owner.get("owner_name"):
                                owner_val = res_owner.get("owner_name")

                        item = {
                            "county": county,
                            "apn": row_apn,
                            "owner": owner_val,
                            "opportunity_tier": scores["opportunity_tier"],
                            "seller_intent_score": scores["seller_intent_score"],
                            "equity_ratio": scores["equity_ratio"],
                            "lien_risk": scores["lien_risk"],
                            "situs": row.get("situs") or row.get("address") or row.get("SITEADDRESS1") or row.get("situs_address") or "No Situs Address",
                            "raw_row": row,
                        }
                        scored_parcels.append(item)

                # Sort by highest Seller Intent Score & Equity Ratio
                scored_parcels = sorted(scored_parcels, key=lambda x: (x["seller_intent_score"], x["equity_ratio"]), reverse=True)

                # Select top_n predictive parcels
                top_parcels = scored_parcels[:top_n]
                results["pre_auction_intel"].extend(top_parcels)

                if generate_reports:
                    for item in top_parcels:
                        rf = build_property_intelligence_dossier(item["raw_row"], county)
                        results["reports_generated"].append(str(rf.resolve()))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="CA-UNIFY Universal 58-County Query Engine")
    parser.add_argument("--county", type=str, help="County key (e.g. humboldt, tehama, butte, fresno, shasta, kern, all)")
    parser.add_argument("--apn", type=str, help="Filter by specific APN")
    parser.add_argument("--type", choices=["all", "excess", "prop_intel"], default="all", help="Lead type")
    parser.add_argument("--out-of-state-heirs", action="store_true", help="Filter for out-of-state heir claims")
    parser.add_argument("--skip-circuit-breaker", action="store_true", help="Skip pre-flight probe")
    parser.add_argument("--generate-reports", action="store_true", help="Build report files in output/dashboard/")
    parser.add_argument("--top", type=int, default=50, help="Top N predictive parcels to report")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON result")
    args = parser.parse_args()

    res = query_county_data(
        county_key=args.county,
        apn=args.apn,
        lead_type=args.type,
        out_of_state_only=args.out_of_state_heirs,
        run_circuit_breaker=not args.skip_circuit_breaker,
        generate_reports=args.generate_reports,
        top_n=args.top,
    )

    if args.json:
        print(json.dumps(res, indent=2))
        return 0

    print("=" * 65)
    print(" CA-UNIFY PREDICTIVE INTELLIGENCE QUERY ENGINE")
    print("=" * 65)
    print(f" Counties Searched     : {', '.join(res['counties_searched'])}")
    print(f" Excess Proceeds Found : {len(res['excess_proceeds'])}")
    print(f" Prop Intel Found      : {len(res['pre_auction_intel'])}")
    print(f" Reports Generated     : {len(res['reports_generated'])}")
    print("=" * 65)

    if res["excess_proceeds"]:
        print("\n--- TOP EXCESS PROCEEDS CLAIMS ---")
        for item in res["excess_proceeds"][:5]:
            print(f"  [{item['county'].upper()}] APN: {item['apn']} | Owner: {item['owner']}")
            print(f"     Excess: ${item['excess_proceeds']:,.2f} | Deadline: {item['claim_deadline']} | Score: {item['recoverability_score']}/100")
            print(f"     Urgency: {item['urgency_status']}")
            print()

    if res["pre_auction_intel"]:
        print("\n--- TOP PREDICTIVE PRE-AUCTION PARCELS (PRE-LIST DISCOVERY) ---")
        for item in res["pre_auction_intel"][:5]:
            print(f"  [{item['county'].upper()}] APN: {item['apn']} | Owner: {item['owner']}")
            print(f"     Tier: {item['opportunity_tier']} | Intent Score: {item['seller_intent_score']}/100 | Equity: {item['equity_ratio']*100:.1f}%")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
