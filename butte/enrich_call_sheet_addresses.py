"""
Fills situs_address, mailing_address, and (where missing) owner name on
butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv by hitting the Butte MBAP
AsrPrint and TaxBillv2 endpoints for each APN.

Reuses the proven fetchers from tax_pipeline.stage4_owner_enrich rather
than reimplementing scraping.

Never overwrites an existing verified_current_owner_name (recorder-chain
grantee wins over assessor assessee_name — the recorder chain is the
authoritative "who owns it right now" signal). Only fills blanks.
"""
import os
import re
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tax_pipeline.stage4_owner_enrich import fetch_asr_print, fetch_mailing_address
from verification.writer import VerificationRun

CALL_SHEET = os.path.join(os.path.dirname(__file__), "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
DELAY = 0.6

# Sources this stage attempts per parcel. Used for completeness scoring.
STAGE_SOURCES = ["asr_print", "taxbill_v2"]


def _apn12(dashed_or_padded: str) -> str:
    return "".join(c for c in str(dashed_or_padded) if c.isdigit()).zfill(12)


def _blank(val) -> bool:
    if val is None:
        return True
    if pd.isna(val):
        return True
    s = str(val).strip()
    return s == "" or s.lower() in {"nan", "none", "unknown"}


CITY_STATE_ZIP_RE = re.compile(r"^[A-Z .'-]+\s+([A-Z]{2})\s+\d{5}(-\d{4})?$")


def _clean_mailing(raw: str) -> tuple[str, str]:
    """
    stage4's fetch_mailing_address returns everything between LOCATION: and
    TAX RATE AREA:, which for Butte includes legal desc + situs street +
    mailing street + mailing city/zip, pipe-separated. The last two
    segments before "TAX RATE AREA:" are always [mailing_street, mailing_csz].

    Returns (mailing_address, state) — state is empty if not parseable.
    """
    if not raw:
        return "", ""
    parts = [p.strip() for p in raw.split("|") if p.strip() and p.strip() != "TAX RATE AREA:"]
    if len(parts) < 2:
        return "", ""
    csz = parts[-1]
    street = parts[-2]
    m = CITY_STATE_ZIP_RE.match(csz)
    if not m:
        # Fallback: don't guess, return raw so caller can inspect
        return raw, ""
    return f"{street}, {csz}", m.group(1)


def enrich(csv_path: str = CALL_SHEET, limit: int | None = None, cycle_label: str | None = None) -> None:
    df = pd.read_csv(csv_path, dtype=str)
    print(f"Loaded {len(df)} rows from {os.path.basename(csv_path)}")

    for col in ("situs_address", "mailing_address", "owner_state", "out_of_state"):
        if col not in df.columns:
            df[col] = ""

    rows = df.head(limit) if limit else df
    total = len(rows)
    recovered_owners = 0
    filled_situs = 0
    filled_mailing = 0
    errors = 0

    with VerificationRun(
        county="butte",
        cycle_label=cycle_label or "butte auction address enrichment",
        input_source=os.path.basename(csv_path),
        parcel_count=total,
    ) as run:
        print(f"  verification run id: {run.run_id}")

        for i, idx in enumerate(rows.index, start=1):
            apn_raw = df.at[idx, "apn"]
            apn = _apn12(apn_raw)
            current_owner = df.at[idx, "verified_current_owner_name"]
            needs_owner = _blank(current_owner)
            needs_situs = _blank(df.at[idx, "situs_address"])
            needs_mailing = _blank(df.at[idx, "mailing_address"])

            # Track per-parcel source success so completeness scores are honest.
            sources_succeeded: list[str] = []

            # Even if all 3 fields are already filled from prior stages,
            # still record provenance so downstream layers can reason about them.
            if not (needs_owner or needs_situs or needs_mailing):
                # Record what we already have (came from recorder chain earlier)
                if not _blank(current_owner):
                    run.record_field(apn_raw, "owner_name", current_owner,
                                     source="recorder_chain_grantee", confidence=0.9,
                                     notes="pre-existing from butte_stage2_pipeline")
                if not _blank(df.at[idx, "mailing_address"]):
                    run.record_field(apn_raw, "mailing_address", df.at[idx, "mailing_address"],
                                     source="taxbill_v2", confidence=0.85,
                                     notes="pre-existing from prior enrichment")
                    sources_succeeded.append("taxbill_v2")
                if not _blank(df.at[idx, "situs_address"]):
                    run.record_field(apn_raw, "situs_address", df.at[idx, "situs_address"],
                                     source="asr_print", confidence=0.9,
                                     notes="pre-existing from prior enrichment")
                    sources_succeeded.append("asr_print")
                run.record_parcel(apn_raw,
                                   sources_expected=STAGE_SOURCES,
                                   sources_succeeded=sources_succeeded)
                continue

            print(f"[{i}/{total}] {apn_raw} ...", end=" ", flush=True)

            try:
                asr = fetch_asr_print(apn, "butte")
                sources_succeeded.append("asr_print")
            except Exception as e:
                errors += 1
                run.record_flag(apn_raw, "completeness", "ASR_FETCH_ERROR",
                                 severity="error", message=f"{type(e).__name__}: {str(e)[:120]}")
                print(f"ASR ERR: {type(e).__name__}: {str(e)[:80]}")
                run.record_parcel(apn_raw,
                                   sources_expected=STAGE_SOURCES,
                                   sources_succeeded=sources_succeeded)
                continue
            time.sleep(DELAY)

            if needs_owner and asr.get("assessee_name"):
                df.at[idx, "verified_current_owner_name"] = asr["assessee_name"]
                df.at[idx, "owner_vesting_confidence"] = "0.7"
                run.record_field(apn_raw, "owner_name", asr["assessee_name"],
                                 source="asr_assessee", confidence=0.7,
                                 notes="assessor fallback; recorder chain was empty")
                recovered_owners += 1
            elif not _blank(current_owner):
                # Existing owner from earlier stage (recorder chain) — record it too
                run.record_field(apn_raw, "owner_name", current_owner,
                                 source="recorder_chain_grantee", confidence=0.9)

            if needs_situs and asr.get("situs_full"):
                df.at[idx, "situs_address"] = asr["situs_full"]
                run.record_field(apn_raw, "situs_address", asr["situs_full"],
                                 source="asr_print", confidence=0.9)
                filled_situs += 1
            elif needs_situs:
                run.record_flag(apn_raw, "completeness", "MISSING_SITUS", "info",
                                 "AsrPrint returned no situs (likely vacant lot)")

            try:
                bill = fetch_mailing_address(apn, "CS", "butte")
                sources_succeeded.append("taxbill_v2")
            except Exception as e:
                errors += 1
                run.record_flag(apn_raw, "completeness", "TAXBILL_FETCH_ERROR",
                                 severity="error", message=f"{type(e).__name__}: {str(e)[:120]}")
                print(f"MAIL ERR: {type(e).__name__}: {str(e)[:80]}")
                df.to_csv(csv_path, index=False)
                run.record_parcel(apn_raw,
                                   sources_expected=STAGE_SOURCES,
                                   sources_succeeded=sources_succeeded)
                continue
            time.sleep(DELAY)

            if needs_mailing and bill.get("mailing_address_raw"):
                cleaned, state = _clean_mailing(bill["mailing_address_raw"])
                df.at[idx, "mailing_address"] = cleaned
                df.at[idx, "owner_state"] = state
                df.at[idx, "out_of_state"] = "Y" if state and state != "CA" else "N"
                # Confidence lower when regex didn't cleanly parse to state
                confidence = 0.85 if state else 0.5
                run.record_field(apn_raw, "mailing_address", cleaned,
                                 source="taxbill_v2", confidence=confidence,
                                 notes=None if state else "mailing_address regex fallback; not parsed to state")
                if not state:
                    run.record_flag(apn_raw, "consistency", "MAILING_STATE_UNPARSED", "warn",
                                     f"raw mailing did not match city/state/zip regex")
                filled_mailing += 1
            elif needs_mailing:
                run.record_flag(apn_raw, "completeness", "MISSING_MAILING", "warn",
                                 "TaxBillv2 returned no mailing address block")
            elif not _blank(df.at[idx, "mailing_address"]):
                # Pre-existing mailing (didn't need filling) — record provenance
                run.record_field(apn_raw, "mailing_address", df.at[idx, "mailing_address"],
                                 source="taxbill_v2", confidence=0.85,
                                 notes="pre-existing from prior enrichment")

            # Backfill provenance for owner/situs that were already populated
            # but the write branch above skipped (because they didn't need filling)
            if not needs_situs and not _blank(df.at[idx, "situs_address"]):
                run.record_field(apn_raw, "situs_address", df.at[idx, "situs_address"],
                                 source="asr_print", confidence=0.9,
                                 notes="pre-existing from prior enrichment")

            got = []
            if asr.get("assessee_name"):
                got.append(f"owner={asr['assessee_name'][:20]}")
            if asr.get("situs_full"):
                got.append("situs")
            if bill.get("mailing_address_raw"):
                got.append("mail")
            print(", ".join(got) or "no data")

            run.record_parcel(apn_raw,
                               sources_expected=STAGE_SOURCES,
                               sources_succeeded=sources_succeeded)

            if i % 25 == 0:
                df.to_csv(csv_path, index=False)
                print(f"  --> checkpointed ({i}/{total})")

        df.to_csv(csv_path, index=False)
        summary = run.summary()

    print()
    print(f"Done. {total} rows processed.")
    print(f"  Recovered owner names: {recovered_owners}")
    print(f"  Filled situs address:  {filled_situs}")
    print(f"  Filled mailing addr:   {filled_mailing}")
    print(f"  Errors:                {errors}")
    print(f"Saved to {csv_path}")
    print()
    print(f"Verification run {run.run_id} summary:")
    print(f"  parcels tracked:      {summary['parcels']}")
    print(f"  completeness avg:     {summary['completeness_avg']:.1f}%" if summary['completeness_avg'] else "  completeness avg:     -")
    print(f"  flags (warn+error):   {summary['flags_open']}")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="Process only first N rows (for smoke test)")
    p.add_argument("--csv", default=CALL_SHEET, help="Path to call sheet CSV")
    args = p.parse_args()
    enrich(args.csv, args.limit)
