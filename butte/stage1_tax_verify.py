import os
import sys
import time
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from butte.butte_tax_api import ButteTaxClient, to_dashed, to_undashed


STAGE1_COLUMNS = [
    "asmt", "apn_dash", "address", "county",
    "parcel_number", "roll_year", "assessment", "tax_year", "roll_category",
    "address_verified", "document_number_raw",
    "v_total_due", "v_total_paid", "v_total_balance",
    "v_delinquent", "default_number", "default_balance", "default_balance_numeric",
    "pay_plan_in_effect", "annual_payment",
    "default_balance_button_text", "default_alert_text",
    "verified_url", "verified_at", "error",
]


def run_retry_errors(input_csv):
    """Re-run only rows that had errors in the previous VERIFIED output."""
    verified_csv = input_csv.replace(".csv", "_VERIFIED.csv")
    if not os.path.exists(verified_csv):
        print("No verified file found at %s" % verified_csv)
        return

    vdf = pd.read_csv(verified_csv)
    error_mask = vdf["error"].astype(str).str.len().gt(0) & (vdf["error"] != "No data parsed")
    retry_df = vdf[error_mask].copy()
    print("Found %d error rows to retry (excluding 'No data parsed')." % len(retry_df))
    if len(retry_df) == 0:
        print("Nothing to retry.")
        return

    # Remove error rows from the original, we'll merge back after
    good_df = vdf[~error_mask].copy()
    print("Keeping %d good rows from previous run." % len(good_df))

    checkpoint_file = input_csv.replace(".csv", "_RETRY_partial.parquet")
    processed = set()
    results = []

    if os.path.exists(checkpoint_file):
        edf = pd.read_parquet(checkpoint_file)
        results = edf.to_dict("records")
        processed = set(str(a) for a in edf["asmt"].dropna().tolist())
        print("Resuming from checkpoint: %d already processed." % len(processed))

    total = len(retry_df)
    errors = 0
    start_time = time.time()

    client = ButteTaxClient(roll_year=2026, delay_between_requests=0.5)

    try:
        for i, row in retry_df.iterrows():
            asmt = row.get("asmt")
            if pd.isna(asmt) or not asmt:
                continue
            asmt_str = str(int(asmt)) if isinstance(asmt, float) else str(asmt).strip()
            if asmt_str in processed:
                continue

            idx = len(processed) + 1
            print("(%d/%d) %s ... " % (idx, total, asmt_str), end="", flush=True)

            tax_result = None
            try:
                dashed = to_dashed(asmt_str)
                tax_result = client.get_detail(dashed)
            except Exception as e:
                errors += 1
                err_msg = str(e)[:200]
                print("ERR: %s" % err_msg)
                tax_data = {
                    "verified_url": "",
                    "v_total_due": None, "v_total_paid": None,
                    "v_total_balance": None, "v_delinquent": False,
                    "v_document_number": None, "v_defaulted_balance": None,
                    "document_number_raw": "", "default_number": "",
                    "pay_plan_in_effect": "", "annual_payment": "",
                    "default_balance": "", "default_balance_numeric": 0.0,
                    "default_balance_button_text": "", "default_alert_text": "",
                    "total_due": "", "total_paid": "", "total_balance": "",
                    "owner_name": None,
                    "error": err_msg,
                }
                combined = row.to_dict()
                combined.update(tax_data)
                combined["verified_at"] = datetime.utcnow().isoformat()
                results.append(combined)
                processed.add(asmt_str)
                continue

            if tax_result is None:
                errors += 1
                tax_data = {
                    "verified_url": "",
                    "v_total_due": None, "v_total_paid": None,
                    "v_total_balance": None, "v_delinquent": False,
                    "document_number_raw": "", "default_number": "",
                    "pay_plan_in_effect": "", "annual_payment": "",
                    "default_balance": "", "default_balance_numeric": 0.0,
                    "default_balance_button_text": "", "default_alert_text": "",
                    "total_due": "", "total_paid": "", "total_balance": "",
                    "owner_name": None,
                    "error": "No data parsed",
                }
            else:
                parcel12 = to_undashed(asmt_str)
                detail_url = "/MBC/butte/tax/main/%s/2026/0000" % parcel12
                recs = tax_result.defaulted_taxes
                first = recs[0] if recs else None
                def_bal = first.balance if first else ""
                try:
                    def_bal_num = float(def_bal.replace("$", "").replace(",", ""))
                except (ValueError, AttributeError):
                    def_bal_num = 0.0
                tax_data = {
                    "verified_url": detail_url,
                    "v_total_due": None,
                    "v_total_paid": None,
                    "v_total_balance": tax_result.total_defaulted_balance,
                    "v_delinquent": tax_result.is_delinquent,
                    "document_number_raw": tax_result.document_number_raw,
                    "v_document_number": tax_result.document_number_raw or None,
                    "default_number": first.default_number if first else "",
                    "pay_plan_in_effect": first.pay_plan_in_effect if first else "",
                    "annual_payment": first.annual_payment if first else "",
                    "default_balance": def_bal,
                    "default_balance_numeric": def_bal_num,
                    "default_balance_button_text": "",
                    "default_alert_text": "",
                    "total_due": None,
                    "total_paid": None,
                    "total_balance": tax_result.total_defaulted_balance,
                    "owner_name": None,
                    "error": "",
                }

            combined = row.to_dict()
            combined.update(tax_data)
            combined["verified_at"] = datetime.utcnow().isoformat()
            results.append(combined)
            processed.add(asmt_str)

            doc = tax_data.get("document_number_raw") or "NO_DOC"
            defn = tax_data.get("default_number") or "-"
            delinq = "Y" if tax_data.get("v_delinquent") else "N"
            err = " ERR" if tax_data.get("error") else ""
            print("Doc=%s Def=%s Del=%s%s" % (str(doc)[:15], defn[:12], delinq, err))

            if len(processed) % 100 == 0:
                pd.DataFrame(results).to_parquet(checkpoint_file)
                elapsed = time.time() - start_time
                rate = len(processed) / elapsed * 60
                print("--> Checkpointed %d records (%.1f/min, %d errors)" % (len(processed), rate, errors))
    finally:
        client.close()

    retry_results = pd.DataFrame(results)
    fixed = retry_results[retry_results["error"].astype(str).str.len() == 0]
    still_err = retry_results[retry_results["error"].astype(str).str.len() > 0]
    print("\nRetry complete: %d fixed, %d still have errors" % (len(fixed), len(still_err)))

    # Merge: good rows + fixed retry rows + still-bad rows
    final = pd.concat([good_df, retry_results], ignore_index=True)
    final.drop_duplicates(subset=["asmt"], keep="last", inplace=True)

    out_name = input_csv.replace(".csv", "_VERIFIED.csv")
    final.to_csv(out_name, index=False)
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    n = len(final)
    has_doc = final["document_number_raw"].astype(str).str.len().gt(0).sum() if "document_number_raw" in final else 0
    has_def = (final["default_number"].astype(str).str.len() > 0).sum() if "default_number" in final else 0
    print("Saved %d records to %s" % (n, out_name))
    print("Health: %d/%d have doc (%.1f%%), %d/%d have default (%.1f%%)" % (
        has_doc, n, has_doc / n * 100 if n else 0,
        has_def, n, has_def / n * 100 if n else 0))


def run_stage1(input_csv, max_records=None, retry_errors=False):
    if retry_errors:
        return run_retry_errors(input_csv)
    print("Starting Stage 1 Tax Verification (httpx) on %s..." % input_csv)
    df = pd.read_csv(input_csv)

    if max_records:
        df = df.head(max_records)

    checkpoint_file = input_csv.replace(".csv", "_VERIFIED_partial.parquet")
    processed = set()
    results = []

    if os.path.exists(checkpoint_file):
        edf = pd.read_parquet(checkpoint_file)
        results = edf.to_dict("records")
        processed = set(str(a) for a in edf["asmt"].dropna().tolist())
        print("Resuming from checkpoint: %d already processed." % len(processed))

    total = len(df)
    errors = 0
    start_time = time.time()

    client = ButteTaxClient(roll_year=2026, delay_between_requests=0.3)

    try:
        for i, row in df.iterrows():
            asmt = row.get("asmt")
            if pd.isna(asmt) or not asmt:
                continue
            asmt_str = str(int(asmt)) if isinstance(asmt, float) else str(asmt).strip()
            if asmt_str in processed:
                continue

            idx = i + 1
            print("(%d/%d) %s ... " % (idx, total, asmt_str), end="", flush=True)

            tax_result = None
            try:
                dashed = to_dashed(asmt_str)
                tax_result = client.get_detail(dashed)
            except Exception as e:
                errors += 1
                err_msg = str(e)[:200]
                print("ERR: %s" % err_msg)
                tax_data = {
                    "verified_url": "",
                    "v_total_due": None, "v_total_paid": None,
                    "v_total_balance": None, "v_delinquent": False,
                    "v_document_number": None, "v_defaulted_balance": None,
                    "document_number_raw": "", "default_number": "",
                    "pay_plan_in_effect": "", "annual_payment": "",
                    "default_balance": "", "default_balance_numeric": 0.0,
                    "default_balance_button_text": "", "default_alert_text": "",
                    "total_due": "", "total_paid": "", "total_balance": "",
                    "owner_name": None,
                    "error": err_msg,
                }
                combined = row.to_dict()
                combined.update(tax_data)
                combined["verified_at"] = datetime.utcnow().isoformat()
                results.append(combined)
                processed.add(asmt_str)
                continue

            if tax_result is None:
                errors += 1
                tax_data = {
                    "verified_url": "",
                    "v_total_due": None, "v_total_paid": None,
                    "v_total_balance": None, "v_delinquent": False,
                    "document_number_raw": "", "default_number": "",
                    "pay_plan_in_effect": "", "annual_payment": "",
                    "default_balance": "", "default_balance_numeric": 0.0,
                    "default_balance_button_text": "", "default_alert_text": "",
                    "total_due": "", "total_paid": "", "total_balance": "",
                    "owner_name": None,
                    "error": "No data parsed",
                }
            else:
                parcel12 = to_undashed(asmt_str)
                detail_url = "/MBC/butte/tax/main/%s/2026/0000" % parcel12
                recs = tax_result.defaulted_taxes
                first = recs[0] if recs else None
                def_bal = first.balance if first else ""
                try:
                    def_bal_num = float(def_bal.replace("$", "").replace(",", ""))
                except (ValueError, AttributeError):
                    def_bal_num = 0.0
                tax_data = {
                    "verified_url": detail_url,
                    "v_total_due": None,
                    "v_total_paid": None,
                    "v_total_balance": tax_result.total_defaulted_balance,
                    "v_delinquent": tax_result.is_delinquent,
                    "document_number_raw": tax_result.document_number_raw,
                    "v_document_number": tax_result.document_number_raw or None,
                    "default_number": first.default_number if first else "",
                    "pay_plan_in_effect": first.pay_plan_in_effect if first else "",
                    "annual_payment": first.annual_payment if first else "",
                    "default_balance": def_bal,
                    "default_balance_numeric": def_bal_num,
                    "default_balance_button_text": "",
                    "default_alert_text": "",
                    "total_due": None,
                    "total_paid": None,
                    "total_balance": tax_result.total_defaulted_balance,
                    "owner_name": None,
                    "error": "",
                }

            combined = row.to_dict()
            combined.update(tax_data)
            combined["verified_at"] = datetime.utcnow().isoformat()
            results.append(combined)
            processed.add(asmt_str)

            doc = tax_data.get("document_number_raw") or "NO_DOC"
            defn = tax_data.get("default_number") or "-"
            delinq = "Y" if tax_data.get("v_delinquent") else "N"
            err = " ERR" if tax_data.get("error") else ""
            print("Doc=%s Def=%s Del=%s%s" % (str(doc)[:15], defn[:12], delinq, err))

            if len(processed) % 100 == 0:
                pd.DataFrame(results).to_parquet(checkpoint_file)
                elapsed = time.time() - start_time
                rate = len(processed) / elapsed * 60
                print("--> Checkpointed %d records (%.1f/min, %d errors)" % (len(processed), rate, errors))
    finally:
        client.close()

    out_df = pd.DataFrame(results)
    if max_records:
        out_name = input_csv.replace(".csv", "_TEST_VERIFIED.csv")
    else:
        out_name = input_csv.replace(".csv", "_VERIFIED.csv")

    out_df.to_csv(out_name, index=False)
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    elapsed = time.time() - start_time
    has_doc = out_df["document_number_raw"].astype(str).str.len().gt(0).sum() if "document_number_raw" in out_df else 0
    has_def = (out_df["default_number"].astype(str).str.len() > 0).sum() if "default_number" in out_df else 0
    n = len(out_df)
    print("\nSaved %d verified records to %s" % (n, out_name))
    print("Time: %.1f min | Rate: %.1f/min" % (elapsed / 60, n / elapsed * 60))
    print("Health: %d/%d have doc number (%.1f%%), %d/%d have default (%.1f%%), %d errors" % (
        has_doc, n, has_doc / n * 100 if n else 0,
        has_def, n, has_def / n * 100 if n else 0, errors))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run only first 10 records")
    parser.add_argument("--retry-errors", action="store_true", help="Re-run only rows with errors from previous VERIFIED.csv")
    parser.add_argument("input_csv", nargs="?", default=os.path.join(os.path.dirname(__file__), "butte_15_percent_sample.csv"))
    args = parser.parse_args()

    if args.test:
        run_stage1(args.input_csv, max_records=10)
    elif args.retry_errors:
        run_stage1(args.input_csv, retry_errors=True)
    else:
        run_stage1(args.input_csv)
