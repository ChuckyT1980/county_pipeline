"""
enrich_auction_list.py

Runs ALL 105 real Aug 7-10 auction parcels through the full Butte pipeline
(ButteTaxClient + TylerRecorderClient), not just the 14 that happened to
overlap with the original 487-parcel sample. The auction list is smaller,
fully dated, and every parcel on it is ALREADY confirmed delinquent enough
to reach auction - so this is arguably a higher-value target list than the
original sample.

Reuses process_one_parcel() from butte_stage2_pipeline.py directly rather
than duplicating the tax+recorder logic - same tested code path, same
integrity gate discipline.

Usage:
    python enrich_auction_list.py
    (auction list is embedded below - update each cycle, see the manual)
"""

import re
import sys
import os

# Add parent directory to path so we can find tyler_recorder_client, etc.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from butte_tax_api import ButteTaxClient
from tyler_recorder_client import TylerRecorderClient, BUTTE
from tax_pipeline.integrity_gate import IntegrityGate
from butte_stage2_pipeline import process_one_parcel

# Same raw list as match_auction_list.py - kept in sync manually each cycle.
AUCTION_LIST_RAW = """
1293645 001-081-006-000
1293646 001-081-007-000
1293647 001-081-018-000
1293648 022-210-078-000
1293649 026-111-008-000
1293650 027-120-038-000
1293651 027-290-021-000
1293652 031-243-024-000
1293653 031-281-137-000
1293654 033-067-003-000
1293655 033-232-003-000
1293656 033-232-022-000
1293657 033-232-025-000
1293658 033-232-026-000
1293659 035-073-020-000
1293660 035-083-006-000
1293661 035-098-011-000
1293662 035-112-009-000
1293663 035-143-011-000
1293664 035-155-019-000
1293665 035-191-010-000
1293666 041-260-027-000
1293667 050-040-132-000
1293668 050-120-121-000
1293669 051-072-071-000
1293670 051-083-079-000
1293671 051-171-067-000
1293672 051-280-005-000
1293673 052-011-094-000
1293674 052-031-040-000
1293675 052-040-067-000
1293676 052-080-054-000
1293677 052-250-052-000
1293678 052-290-079-000
1293679 052-290-161-000
1293680 053-021-067-000
1293681 053-180-086-000
1293682 053-340-041-000
1293683 054-161-037-000
1293684 054-192-095-000
1293685 054-260-006-000
1293686 055-130-089-000
1293687 055-330-017-000
1293688 055-520-085-000
1293689 056-400-019-000
1293690 058-260-060-000
1293691 058-330-038-000
1293692 058-330-046-000
1293693 058-370-023-000
1293694 058-370-027-000
1293695 058-370-048-000
1293696 058-410-029-000
1293697 058-430-019-000
1293698 059-087-011-000
1293699 059-087-017-000
1293700 059-092-008-000
1293701 061-550-017-000
1293702 061-550-018-000
1293703 061-590-007-000
1293704 061-590-009-000
1293705 061-610-005-000
1293706 061-610-009-000
1293707 062-140-027-000
1293708 062-150-008-000
1293709 062-150-009-000
1293710 062-190-025-000
1293711 062-190-029-000
1293712 062-300-005-000
1293713 062-300-006-000
1293714 062-300-007-000
1293715 062-300-033-000
1293716 062-300-044-000
1293717 062-300-077-000
1293718 062-300-078-000
1293719 062-310-012-000
1293720 062-320-006-000
1293721 062-320-008-000
1293722 062-320-018-000
1293723 062-320-029-000
1293724 062-340-018-000
1293725 062-350-024-000
1293726 062-690-027-000
1293727 062-710-019-000
1293728 062-730-008-000
1293729 062-750-036-000
1293730 065-210-023-000
1293731 066-050-011-000
1293732 066-100-010-000
1293733 066-130-036-000
1293734 066-220-001-000
1293735 066-230-047-000
1293736 066-270-036-000
1293737 066-420-011-000
1293738 069-190-021-000
1293739 071-060-021-000
1293740 071-060-025-000
1293741 071-150-003-000
1293742 071-240-025-000
1293743 071-270-029-000
1293744 071-270-045-000
1293745 071-280-038-000
1293746 071-320-003-000
1293747 071-470-021-000
1293748 072-190-015-000
1293749 072-200-034-000
"""

CHECK_EVERY = 25   # tighter window than the 487-record run — this batch is
                    # small and high-value, catch any problem fast
MIN_HIT_RATE = 0.30  # PLACEHOLDER — same calibration note as butte_stage2_pipeline.py


def parse_auction_list(raw: str) -> list[dict]:
    rows = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"(\d+)\s+([\d\-]+)", line)
        if m:
            auction_id, apn_dashed = m.groups()
            rows.append({"auction_id": auction_id, "apn_dashed": apn_dashed})
    return rows


def run(output_csv: str = "butte_auction_105_ENRICHED.csv",
        already_enriched_csv: str = "butte_SCORED_AUCTION_MATCHES.csv"):
    all_parcels = parse_auction_list(AUCTION_LIST_RAW)
    print(f"Parsed {len(all_parcels)} total auction parcels.")

    # Skip parcels we already have real, tested enrichment data for —
    # no reason to re-hit the live site for the 14 we already confirmed.
    #
    # IMPORTANT: re-normalize on load, don't trust the stored value.
    # Confirmed real bug: pandas silently strips leading zeros when
    # reading back a CSV column that's all-digits (infers int64), even
    # though it was written as a zero-padded string. Same root cause as
    # the original 'apn' column issue - this is the SAME bug recurring on
    # a DIFFERENT column, worth remembering this pattern can bite any
    # all-digit ID column round-tripped through CSV, not just 'apn'.
    already_done_apns = set()
    existing_rows = []
    try:
        existing_df = pd.read_csv(already_enriched_csv, dtype=str)
        if "apn_normalized" in existing_df.columns:
            already_done_apns = set(
                existing_df["apn_normalized"].astype(str).str.zfill(12)
            )
        elif "apn" in existing_df.columns:
            already_done_apns = set(
                re.sub(r"\D", "", str(a)).zfill(12) for a in existing_df["apn"]
            )
        existing_rows = existing_df.to_dict("records")
        print(f"Found {len(already_done_apns)} already-enriched parcels in {already_enriched_csv} — skipping those.")
    except FileNotFoundError:
        print(f"No existing file at {already_enriched_csv} — will fetch all {len(all_parcels)}.")

    parcels_to_fetch = [
        p for p in all_parcels
        if p["apn_dashed"].replace("-", "").zfill(12) not in already_done_apns
    ]
    print(f"Fetching {len(parcels_to_fetch)} remaining parcels (skipped {len(all_parcels) - len(parcels_to_fetch)}).\n")

    if not parcels_to_fetch:
        print("Nothing new to fetch — all 105 already covered.")
        return

    tax_client = ButteTaxClient()
    recorder_client = TylerRecorderClient(BUTTE)

    gate = IntegrityGate(
        check_every=CHECK_EVERY,
        input_doc_field="doc_fmt",
        min_hit_rate=MIN_HIT_RATE,
        county="butte_auction_105",
        history_file="butte_auction_integrity_history.jsonl",
    )

    results_list = []
    error_count = 0

    try:
        for i, parcel in enumerate(parcels_to_fetch):
            result_row = process_one_parcel(parcel["apn_dashed"], tax_client, recorder_client)
            result_row["auction_id"] = parcel["auction_id"]
            result_row["auction_apn_dashed"] = parcel["apn_dashed"]
            results_list.append(result_row)

            if result_row["error"]:
                error_count += 1
                print(f"[{i+1}/{len(parcels_to_fetch)}] ERROR on {parcel['apn_dashed']}: {result_row['error']}")

            gate.record(result_row)
            if gate.should_check():
                ok, report = gate.check()
                if not ok:
                    print(report)
                    combined = existing_rows + results_list
                    pd.DataFrame(combined).to_csv(output_csv, index=False)
                    print(f"\nPartial results saved to {output_csv} ({len(combined)} total records)")
                    raise SystemExit(
                        "Integrity gate failed — halting. Fix the issue, then "
                        "resume rather than re-running from scratch."
                    )
                else:
                    print(f"[integrity_gate] OK at record {i+1}\n{report}")

            if (i + 1) % 10 == 0:
                print(f"  ...{i+1}/{len(parcels_to_fetch)} processed, {error_count} errors so far")

        final = gate.finalize()
        if final is not None:
            ok, report = final
            if not ok:
                print(report)
                combined = existing_rows + results_list
                pd.DataFrame(combined).to_csv(output_csv, index=False)
                raise SystemExit("Integrity gate failed on final tail check — halting.")
            else:
                print(f"[integrity_gate] Final tail check OK\n{report}")

    finally:
        tax_client.close()
        recorder_client.close()

    # Merge already-enriched (14) + newly-fetched (91) into one complete file
    combined = existing_rows + results_list
    pd.DataFrame(combined).to_csv(output_csv, index=False)
    print(f"\nDone. {len(results_list)} newly fetched, {len(existing_rows)} reused from existing file.")
    print(f"Total: {len(combined)} / 105 records.")
    print(f"{error_count} errors during this run.")
    print(f"Saved combined file to {output_csv}")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "butte_auction_105_ENRICHED.csv"
    run(output)
