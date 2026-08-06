"""
Enrich the Butte call sheet with tax bill data.

For every APN:
  1. Fetch + save the tax bill HTML
  2. Parse into 12 new fields
  3. Merge into butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv
  4. Log to verification.sqlite for provenance

Adds these columns to the CSV:
  land_value, improvements_value, net_taxable_value, total_tax_billed,
  original_bill_date, power_to_sell_date, years_since_power_to_sell,
  redemption_status, redemption_date, homeowner_exemption,
  installment_plan_active, special_assessments_total,
  special_assessments_list, tax_bill_important_messages
"""
import os
import sys
import time
from dataclasses import asdict

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from butte.tax_bill import enrich_apn
from verification.writer import VerificationRun

CALL_SHEET = os.path.join(os.path.dirname(__file__), "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
DELAY = 0.5

NEW_COLS = [
    "land_value", "improvements_value", "net_taxable_value", "total_tax_billed",
    "original_bill_date", "power_to_sell_date", "years_since_power_to_sell",
    "redemption_status", "redemption_date", "homeowner_exemption",
    "installment_plan_active", "special_assessments_total",
    "special_assessments_list", "tax_bill_important_messages",
]


def run(csv_path: str = CALL_SHEET, limit: int | None = None) -> None:
    df = pd.read_csv(csv_path, dtype=str)
    for col in NEW_COLS:
        if col not in df.columns:
            df[col] = ""

    rows = df.head(limit) if limit else df
    total = len(rows)
    stats = {"ok": 0, "no_data": 0, "error": 0, "redeemed": 0, "still_delinquent": 0,
             "installment_active": 0}

    with VerificationRun(
        county="butte",
        cycle_label="butte tax bill enrichment",
        input_source=os.path.basename(csv_path),
        parcel_count=total,
    ) as run_ctx:
        print(f"Tax bill enrichment run #{run_ctx.run_id} on {total} parcels")

        for i, idx in enumerate(rows.index, start=1):
            apn = df.at[idx, "apn"]
            print(f"[{i}/{total}] {apn} ...", end=" ", flush=True)

            result = enrich_apn(apn)
            time.sleep(DELAY)

            if result.fetch_status == "error":
                stats["error"] += 1
                print("ERROR")
                run_ctx.record_flag(apn, "completeness", "TAXBILL_FETCH_ERROR", "warn",
                                     result.fetch_error)
                continue
            if result.fetch_status == "no_data":
                stats["no_data"] += 1
                print("no data")
                continue

            stats["ok"] += 1

            # Write every parsed field to CSV
            for col in NEW_COLS:
                val = getattr(result, col, None)
                if val is not None and val != "":
                    df.at[idx, col] = str(val)

            # Provenance
            if result.redemption_status:
                run_ctx.record_field(apn, "redemption_status", result.redemption_status,
                                      source="butte_tax_bill", confidence=0.95)
                if result.redemption_status == "redeemed":
                    stats["redeemed"] += 1
                    run_ctx.record_flag(apn, "consistency", "PARCEL_REDEEMED", "warn",
                                         f"Delinquent taxes redeemed {result.redemption_date} — parcel may be OFF auction")
                elif result.redemption_status == "still_delinquent":
                    stats["still_delinquent"] += 1
            if result.installment_plan_active == "Y":
                stats["installment_active"] += 1
                run_ctx.record_flag(apn, "consistency", "INSTALLMENT_PLAN_ACTIVE", "info",
                                     "Owner is on an installment plan — partial motivation")
            if result.total_tax_billed:
                run_ctx.record_field(apn, "total_tax_billed", result.total_tax_billed,
                                      source="butte_tax_bill", confidence=0.9)

            flags = []
            if result.redemption_status == "redeemed":
                flags.append(f"REDEEMED {result.redemption_date}")
            if result.installment_plan_active == "Y":
                flags.append("INSTALLMENT")
            if result.homeowner_exemption == "Y":
                flags.append("HOX")
            if result.years_since_power_to_sell and result.years_since_power_to_sell >= 10:
                flags.append(f"{result.years_since_power_to_sell}y_PTS")
            print(" | ".join(flags) if flags else "ok")

            if i % 20 == 0:
                df.to_csv(csv_path, index=False)
                print(f"  --> checkpointed ({i}/{total})")

        df.to_csv(csv_path, index=False)

    print()
    print("=" * 60)
    print(f"Tax bill enrichment complete. {total} parcels processed.")
    print(f"  OK:                        {stats['ok']}")
    print(f"  No data:                   {stats['no_data']}")
    print(f"  Fetch errors:              {stats['error']}")
    print(f"  --> REDEEMED (off auction?): {stats['redeemed']}  <-- REVIEW THESE")
    print(f"  --> Still delinquent:        {stats['still_delinquent']}")
    print(f"  --> Installment plan active: {stats['installment_active']}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--csv", default=CALL_SHEET)
    args = p.parse_args()
    run(args.csv, args.limit)
