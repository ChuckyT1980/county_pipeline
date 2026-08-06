"""
Environmental enrichment for the Butte auction call sheet: geocode each
situs address, then hit FEMA NFHL (flood zone) and CalFire FHSZ (fire
hazard zone). Writes provenance to verification.sqlite and adds
flood_zone, flood_zone_subtype, fire_hazard_zone, fire_responsibility_area,
geocode_lat, geocode_lon columns to the call sheet CSV.

Skip parcels with no situs_address (typical for vacant land) — those
get a MISSING_SITUS_FOR_GEOCODE flag.
"""
import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from verification.environmental import enrich_point
from verification.writer import VerificationRun

CALL_SHEET = os.path.join(os.path.dirname(__file__), "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")

STAGE_SOURCES = ["geocoder", "fema_nfhl", "calfire_fhsz"]


def _blank(v) -> bool:
    if v is None or pd.isna(v):
        return True
    return str(v).strip().lower() in {"", "nan", "none"}


def run(csv_path: str = CALL_SHEET, limit: int | None = None) -> None:
    df = pd.read_csv(csv_path, dtype=str)
    for col in (
        "flood_zone", "flood_zone_subtype", "fire_hazard_zone",
        "fire_responsibility_area", "geocode_lat", "geocode_lon",
    ):
        if col not in df.columns:
            df[col] = ""

    rows = df.head(limit) if limit else df
    total = len(rows)
    stats = {"geocoded": 0, "flood_ok": 0, "fire_ok": 0, "skipped_no_situs": 0, "geocode_failed": 0}

    with VerificationRun(
        county="butte",
        cycle_label="butte auction environmental enrichment",
        input_source=os.path.basename(csv_path),
        parcel_count=total,
    ) as run_ctx:
        print(f"Environmental enrichment run #{run_ctx.run_id} on {total} parcels")

        for i, idx in enumerate(rows.index, start=1):
            apn = df.at[idx, "apn"]
            situs = df.at[idx, "situs_address"]

            sources_succeeded: list[str] = []

            if _blank(situs):
                stats["skipped_no_situs"] += 1
                run_ctx.record_flag(apn, "completeness", "MISSING_SITUS_FOR_GEOCODE", "info",
                                     "no situs address to geocode (typical for vacant land)")
                run_ctx.record_parcel(apn, sources_expected=STAGE_SOURCES,
                                       sources_succeeded=sources_succeeded)
                continue

            # Skip re-work: if this parcel already has env data, just re-record provenance
            already_done = not _blank(df.at[idx, "flood_zone"]) and not _blank(df.at[idx, "fire_hazard_zone"])
            if already_done:
                run_ctx.record_field(apn, "flood_zone", df.at[idx, "flood_zone"],
                                      source="fema_nfhl", confidence=0.9,
                                      notes="pre-existing from prior enrichment")
                run_ctx.record_field(apn, "fire_hazard_zone", df.at[idx, "fire_hazard_zone"],
                                      source="calfire_fhsz", confidence=0.9,
                                      notes="pre-existing from prior enrichment")
                sources_succeeded.extend(["geocoder", "fema_nfhl", "calfire_fhsz"])
                run_ctx.record_parcel(apn, sources_expected=STAGE_SOURCES,
                                       sources_succeeded=sources_succeeded)
                continue

            print(f"[{i}/{total}] {apn} situs={situs[:40]}...", end=" ", flush=True)
            result = enrich_point(situs, county="Butte")

            if not result["geocode_lat"]:
                stats["geocode_failed"] += 1
                run_ctx.record_flag(apn, "completeness", "GEOCODE_FAILED", "warn",
                                     f"could not geocode: {situs[:80]}")
                run_ctx.record_parcel(apn, sources_expected=STAGE_SOURCES,
                                       sources_succeeded=sources_succeeded)
                print("GEOCODE FAILED")
                continue

            stats["geocoded"] += 1
            sources_succeeded.append("geocoder")
            df.at[idx, "geocode_lat"] = str(result["geocode_lat"])
            df.at[idx, "geocode_lon"] = str(result["geocode_lon"])
            run_ctx.record_field(apn, "geocode", f"({result['geocode_lat']:.5f},{result['geocode_lon']:.5f})",
                                  source="nominatim_or_census", confidence=0.8)

            if result["flood_zone"]:
                df.at[idx, "flood_zone"] = str(result["flood_zone"])
                df.at[idx, "flood_zone_subtype"] = str(result["flood_zone_subtype"] or "")
                run_ctx.record_field(apn, "flood_zone", result["flood_zone"],
                                      source="fema_nfhl", confidence=0.9)
                sources_succeeded.append("fema_nfhl")
                stats["flood_ok"] += 1

            if result["fire_hazard_zone"]:
                df.at[idx, "fire_hazard_zone"] = str(result["fire_hazard_zone"])
                df.at[idx, "fire_responsibility_area"] = str(result["fire_responsibility_area"] or "")
                run_ctx.record_field(apn, "fire_hazard_zone", result["fire_hazard_zone"],
                                      source="calfire_fhsz", confidence=0.9)
                sources_succeeded.append("calfire_fhsz")
                stats["fire_ok"] += 1

            run_ctx.record_parcel(apn, sources_expected=STAGE_SOURCES,
                                   sources_succeeded=sources_succeeded)
            print(f"flood={result['flood_zone']} fire={result['fire_hazard_zone']}")

            if i % 20 == 0:
                df.to_csv(csv_path, index=False)
                print(f"  --> checkpointed ({i}/{total})")

        df.to_csv(csv_path, index=False)
        summary = run_ctx.summary()

    print()
    print(f"Done. {total} parcels processed.")
    print(f"  Geocoded successfully:      {stats['geocoded']}")
    print(f"  Geocode failed:             {stats['geocode_failed']}")
    print(f"  Skipped (no situs):         {stats['skipped_no_situs']}")
    print(f"  Flood zone filled:          {stats['flood_ok']}")
    print(f"  Fire hazard zone filled:    {stats['fire_ok']}")
    print(f"Verification run #{run_ctx.run_id} completeness avg: {summary['completeness_avg']:.1f}%")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--csv", default=CALL_SHEET)
    args = p.parse_args()
    run(args.csv, args.limit)
