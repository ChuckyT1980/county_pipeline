import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import re

INPUT_DOC_FIELD_CANDIDATES = ["doc_fmt", "v_document_number", "document_number"]

# A real doc number is digits plus optionally R/hyphen — never contains letters
# spread across multiple words (that's a name) or the literal word UNKNOWN.
DOC_NUMBER_SHAPE_RE = re.compile(r"^[\dR\-]+$")


def load_file(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    elif p.suffix == ".csv":
        return pd.read_csv(p)
    else:
        raise ValueError(f"Unsupported file type: {p.suffix} (expected .parquet or .csv)")


def find_input_doc_field(df: pd.DataFrame) -> str:
    for candidate in INPUT_DOC_FIELD_CANDIDATES:
        if candidate in df.columns:
            return candidate
    raise ValueError(
        f"None of the expected input doc-number columns found: {INPUT_DOC_FIELD_CANDIDATES}. "
        f"Available columns: {list(df.columns)}"
    )


def verify(df: pd.DataFrame, input_field: str) -> dict:
    total_rows = len(df)
    rows_with_chain = 0
    empty_doc_number = 0
    format_mismatched = 0       # e.g. R vs hyphen — likely benign normalization
    structurally_corrupt = 0    # e.g. a name or "UNKNOWN" in doc_number — REAL bug
    bad_row_indices = []
    corrupt_row_indices = []
    examples = []
    corrupt_examples = []

    for idx, row in df.iterrows():
        chain_raw = row.get("recorder_chain")
        if not chain_raw or pd.isna(chain_raw):
            continue

        try:
            chain = json.loads(chain_raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

        if not chain:
            continue

        rows_with_chain += 1
        input_doc = str(row.get(input_field, "")).strip()
        input_doc_normalized = input_doc.replace("R", "-").replace("--", "-")

        row_is_bad = False
        row_is_corrupt = False
        for event in chain:
            event_doc = str(event.get("doc_number", "")).strip()

            if not event_doc:
                empty_doc_number += 1
                row_is_bad = True
                continue

            if not DOC_NUMBER_SHAPE_RE.match(event_doc):
                # Contains letters other than R, or spaces (a name), or literal UNKNOWN
                structurally_corrupt += 1
                row_is_bad = True
                row_is_corrupt = True
                continue

            if input_doc and event_doc != input_doc and event_doc != input_doc_normalized:
                format_mismatched += 1
                row_is_bad = True

        if row_is_bad:
            bad_row_indices.append(idx)
            if len(examples) < 10:
                examples.append(
                    {
                        "row_index": idx,
                        "input_doc_number": input_doc,
                        "chain_doc_numbers": [e.get("doc_number", "") for e in chain],
                    }
                )
        if row_is_corrupt:
            corrupt_row_indices.append(idx)
            if len(corrupt_examples) < 10:
                corrupt_examples.append(
                    {
                        "row_index": idx,
                        "input_doc_number": input_doc,
                        "full_chain_json": chain_raw,
                    }
                )

    return {
        "total_rows": total_rows,
        "rows_with_chain": rows_with_chain,
        "empty_doc_number_events": empty_doc_number,
        "format_mismatched_events": format_mismatched,
        "structurally_corrupt_events": structurally_corrupt,
        "bad_row_count": len(bad_row_indices),
        "bad_row_indices": bad_row_indices,
        "corrupt_row_count": len(corrupt_row_indices),
        "corrupt_row_indices": corrupt_row_indices,
        "examples": examples,
        "corrupt_examples": corrupt_examples,
    }


def main():
    parser = argparse.ArgumentParser(description="Verify doc_number integrity in Stage 2 output")
    parser.add_argument("input_path", help="Path to .parquet or .csv checkpoint/output file")
    parser.add_argument(
        "--fix-out",
        default=None,
        help="If set, write full rows for all bad records to this CSV for re-processing",
    )
    args = parser.parse_args()

    print(f"Loading {args.input_path} ...")
    df = load_file(args.input_path)

    input_field = find_input_doc_field(df)
    print(f"Using '{input_field}' as the input doc-number field.\n")

    results = verify(df, input_field)

    print("=" * 60)
    print(f"Total rows:                       {results['total_rows']}")
    print(f"Rows with a recorder_chain:        {results['rows_with_chain']}")
    print(f"Empty doc_number events:           {results['empty_doc_number_events']}")
    print(f"Format-mismatched events (R/hyphen): {results['format_mismatched_events']}")
    print(f"STRUCTURALLY CORRUPT events:       {results['structurally_corrupt_events']}  <-- names/UNKNOWN in doc_number, real bug")
    print(f"Bad rows (any issue):              {results['bad_row_count']}")
    print(f"Corrupt rows (names/UNKNOWN):       {results['corrupt_row_count']}")
    print("=" * 60)

    if results["corrupt_examples"]:
        print("\n*** STRUCTURAL CORRUPTION — full chain JSON for inspection ***")
        for ex in results["corrupt_examples"]:
            print(f"\n  row {ex['row_index']}: input={ex['input_doc_number']!r}")
            print(f"  full recorder_chain: {ex['full_chain_json']}")

    if results["examples"]:
        print("\nAll bad-row examples (includes benign format mismatches):")
        for ex in results["examples"]:
            print(f"  row {ex['row_index']}: input={ex['input_doc_number']!r} "
                  f"chain_doc_numbers={ex['chain_doc_numbers']}")

    if args.fix_out and results["bad_row_indices"]:
        bad_df = df.loc[results["bad_row_indices"]]
        bad_df.to_csv(args.fix_out, index=False)
        print(f"\nWrote {len(bad_df)} bad rows to {args.fix_out} for re-processing.")
    elif args.fix_out:
        print("\nNo bad rows found — nothing written.")

    if results["bad_row_count"] == 0 and results["rows_with_chain"] > 0:
        print("\nAll clear — every row's recorder_chain doc_number matches the input.")
        sys.exit(0)
    elif results["bad_row_count"] > 0:
        print(f"\nWARNING: {results['bad_row_count']} rows need attention.")
        sys.exit(1)


if __name__ == "__main__":
    main()
