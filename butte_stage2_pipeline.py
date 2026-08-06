import json
import sys
import time
from dataclasses import asdict

import pandas as pd

from butte_tax_api import ButteTaxClient
from tyler_recorder_client import TylerRecorderClient, BUTTE
from tax_pipeline.integrity_gate import IntegrityGate

CHECK_EVERY = 50            # smaller window than the 100-record default, since
                             # this is a first real batch — catch problems faster
MIN_HIT_RATE = 0.30          # PLACEHOLDER — calibrate against a real batch, see note above
CORRUPT_RATE_THRESHOLD = 0.02


def process_one_parcel(parcel_number: str, tax_client: ButteTaxClient,
                        recorder_client: TylerRecorderClient, original_row: dict = None) -> dict:
    """Returns a result row dict. Never raises for expected 'no data' cases
    (no delinquency, no recorder hit) — only raises for genuine unexpected
    errors, which should surface loudly rather than being swallowed."""
    row = dict(original_row) if original_row else {}
    row.update({
        "parcel_number": parcel_number,
        "v_document_number": "",
        "doc_fmt": "",
        "v_delinquent": False,
        "v_total_balance": 0.0,
        "is_delinquent": False,
        "total_defaulted_balance": 0.0,
        "default_year": None,
        "years_delinquent": None,
        "recorder_chain": json.dumps([]),
        "error": "",
    })

    try:
        tax_result = tax_client.get_detail(parcel_number)
    except Exception as e:
        row["error"] = f"tax_client error: {type(e).__name__}: {e}"
        return row

    if tax_result is None:
        row["error"] = "tax_client returned no data (parcel not found or parse failed)"
        return row

    row["doc_fmt"] = tax_result.document_number_raw
    row["v_document_number"] = tax_result.document_number_raw
    row["is_delinquent"] = tax_result.is_delinquent
    row["v_delinquent"] = tax_result.is_delinquent
    row["total_defaulted_balance"] = tax_result.total_defaulted_balance
    row["v_total_balance"] = tax_result.total_defaulted_balance
    
    if tax_result.defaulted_taxes:
        # Just grab the year/delinquency from the first default record
        row["default_year"] = tax_result.defaulted_taxes[0].default_year
        row["years_delinquent"] = tax_result.defaulted_taxes[0].years_delinquent

    if not tax_result.document_number_raw:
        # No document number on file for this parcel — legitimate "no data"
        # case, not an error. Leave recorder_chain empty and move on.
        return row

    try:
        recorder_client.submit_doc_search(tax_result.document_number_raw)
        results, total = recorder_client.get_results(search_type="doc")
    except Exception as e:
        row["error"] = f"recorder_client error: {type(e).__name__}: {e}"
        return row

    chain = [asdict(r) for r in results]
    row["recorder_chain"] = json.dumps(chain)

    return row


def run(input_csv: str, output_csv: str = None):
    if output_csv is None:
        output_csv = input_csv.replace(".csv", "_ENRICHED.csv")

    df = pd.read_csv(input_csv)
    if "parcel_number" not in df.columns:
        raise ValueError(
            f"Expected a 'parcel_number' column, got: {list(df.columns)}. "
            f"Adjust this script or rename the column before running."
        )

    tax_client = ButteTaxClient()
    recorder_client = TylerRecorderClient(BUTTE)

    gate = IntegrityGate(
        check_every=CHECK_EVERY,
        input_doc_field="doc_fmt",
        min_hit_rate=MIN_HIT_RATE,
        corrupt_rate_threshold=CORRUPT_RATE_THRESHOLD,
        county="butte",
        history_file="butte_integrity_history.jsonl",
    )

    results_list = []
    error_count = 0

    try:
        for i, row in df.iterrows():
            parcel = str(row["parcel_number"])
            result_row = process_one_parcel(parcel, tax_client, recorder_client)
            results_list.append(result_row)

            if result_row["error"]:
                error_count += 1
                print(f"[{i+1}/{len(df)}] ERROR on {parcel}: {result_row['error']}")

            gate.record(result_row)
            if gate.should_check():
                ok, report = gate.check()
                if not ok:
                    print(report)
                    pd.DataFrame(results_list).to_csv(output_csv, index=False)
                    print(f"\nPartial results saved to {output_csv} ({len(results_list)} records)")
                    raise SystemExit(
                        "Integrity gate failed — halting pipeline. "
                        "Fix the underlying issue, then resume rather than "
                        "re-running from scratch (checkpoint is saved above)."
                    )
                else:
                    print(f"[integrity_gate] OK at record {i+1}\n{report}")

            if (i + 1) % 10 == 0:
                print(f"  ...{i+1}/{len(df)} processed, {error_count} errors so far")

    finally:
        tax_client.close()
        recorder_client.close()

    # Confirmed real gap (7/14): a 75-row batch with check_every=50 only
    # ever checked the first 50 records — rows 51-75 ran through the loop
    # unverified. finalize() forces one last check on whatever's left in
    # the window so no record silently escapes the gate.
    final = gate.finalize()
    if final is not None:
        ok, report = final
        if not ok:
            print(report)
            pd.DataFrame(results_list).to_csv(output_csv, index=False)
            print(f"\nResults saved to {output_csv} ({len(results_list)} records)")
            raise SystemExit("Integrity gate failed on final tail check.")
        else:
            print(f"[integrity_gate] Final tail check OK\n{report}")

    pd.DataFrame(results_list).to_csv(output_csv, index=False)
    print(f"\nDone. {len(results_list)} records processed, {error_count} errors.")
    print(f"Saved to {output_csv}")
    print(f"Full integrity history: butte_integrity_history.jsonl")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python butte_stage2_pipeline.py <input_csv>")
        sys.exit(1)
    run(sys.argv[1])
