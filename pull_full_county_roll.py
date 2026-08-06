"""
pull_full_county_roll.py — Production Full County Roll Unified Runner.

Executes the full end-to-end unified pipeline across all 40,059 Tehama master parcels
(or any county's full master index).

Pulls:
  1. MPTS Assessor data (AsrPrint: owner, assessed value, situs address, doc number, sale date)
  2. Tyler Recorder data (Grantor, Grantee, event type, deed chain verification)
  3. Content-addressed raw capture to data/raw/

Usage:
  # Test on 10 parcels:
  python pull_full_county_roll.py --county tehama --limit 10

  # Full production sweep (resumable):
  python pull_full_county_roll.py --county tehama --limit 0 --resume
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from contracts import (
    AdapterError,
    IntegrityError,
    SourceType,
    build_adapters_for_county,
)
from county_config_loader import load_county_config
from http_client import build_http_client
from multi_transform import search_document_with_variants
from normalizers import DefaultNormalizers
from raw_store import FileRawStore

# Register concrete adapters
import arcgis_assessor  # noqa: F401
import mpts_assessor  # noqa: F401
import tehama_recorder_tyler  # noqa: F401

ROOT = Path(__file__).resolve().parent


def load_master_index(csv_path: Path, limit: int = 0) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Master index file not found: {csv_path}")

    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            apn = (r.get("parcel_number") or r.get("apn") or r.get("APN") or r.get("asmt") or "").strip()
            address = (r.get("address") or r.get("situs") or "").strip()
            if apn:
                rows.append({"apn": apn, "situs": address})

    return rows[:limit] if limit > 0 else rows


def load_processed_apns(out_path: Path) -> set[str]:
    processed: set[str] = set()
    if not out_path.exists():
        return processed
    with out_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                apn = rec.get("apn_raw") or rec.get("apn")
                if apn:
                    processed.add(apn)
            except json.JSONDecodeError:
                continue
    return processed


def main() -> int:
    parser = argparse.ArgumentParser(description="Full County Roll Unified Sweep Runner")
    parser.add_argument("--county", type=str, default="tehama", help="County key (e.g. tehama, shasta)")
    parser.add_argument("--index", type=str, help="Master index CSV path")
    parser.add_argument("--out", type=str, help="Output JSONL path")
    parser.add_argument("--limit", type=int, default=10, help="Limit parcel count (0 = ALL)")
    parser.add_argument("--resume", action="store_true", help="Resume sweep by skipping existing APNs")
    parser.add_argument("--delay", type=float, default=1.2, help="Inter-parcel politeness delay in seconds")
    parser.add_argument("--progress-every", type=int, default=25, help="Print progress tally every N parcels")
    args = parser.parse_args()

    county_key = args.county.lower().strip()
    default_index = ROOT / county_key / f"{county_key}_AUTHORITATIVE_master_index.csv"
    index_path = Path(args.index) if args.index else default_index

    if not index_path.exists():
        print(f"[full_roll] Error: Master index not found at {index_path}", file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else (
        ROOT / "data" / county_key / f"{county_key}_full_roll_unified.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    master_parcels = load_master_index(index_path, limit=args.limit)
    print(f"[full_roll] Loaded {len(master_parcels)} master parcels from {index_path.name}")

    processed_apns: set[str] = set()
    file_mode = "w"
    if args.resume:
        processed_apns = load_processed_apns(out_path)
        file_mode = "a"
        if processed_apns:
            master_parcels = [p for p in master_parcels if p["apn"] not in processed_apns]
            print(f"[full_roll] Resume: {len(processed_apns)} APNs already done; {len(master_parcels)} remaining")

    cfg = load_county_config(county_key)
    norm = DefaultNormalizers(home_county=county_key)
    store = FileRawStore(root_dir=str(ROOT / "data"))
    http = build_http_client()

    adapters = build_adapters_for_county(cfg, http, store, norm)
    assessor = adapters.get(SourceType.ASSESSOR)
    recorder = adapters.get(SourceType.RECORDER)

    print(f"[full_roll] Starting sweep for {cfg.display_name} ({len(master_parcels)} parcels)")
    print(f"[full_roll] Out: {out_path.relative_to(ROOT)}")
    print(f"[full_roll] Assessor adapter: {type(assessor).__name__ if assessor else 'NONE'}")
    print(f"[full_roll] Recorder adapter: {type(recorder).__name__ if recorder else 'NONE'}")

    tally = {"assessor_hits": 0, "recorder_hits": 0, "errors": 0}
    start_time = time.time()

    with out_path.open(file_mode, encoding="utf-8") as fh:
        for i, p in enumerate(master_parcels, 1):
            apn = p["apn"]
            situs_seed = p["situs"]

            record: dict = {
                "apn_raw": apn,
                "apn_norm": norm.apn(apn),
                "situs_seed": situs_seed,
                "county": county_key,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "assessor_status": "NONE",
                "recorder_status": "NONE",
                "property": None,
                "snapshot": None,
                "assessee": None,
                "recorder_event": None,
            }

            # 1. Pull Assessor Data
            doc_number_found = ""
            if assessor:
                try:
                    asr_res = assessor.fetch_by_apn(apn)
                    tally["assessor_hits"] += 1
                    record["assessor_status"] = "OK"
                    record["property"] = asr_res.property.model_dump(mode="json")
                    record["snapshot"] = asr_res.snapshot.model_dump(mode="json")
                    record["assessee"] = asr_res.assessee.model_dump(mode="json") if asr_res.assessee else None

                    # Capture document number from last sale if present
                    doc_number_found = (asr_res.snapshot.last_sale_doc_number or "").strip()

                except IntegrityError as exc:
                    record["assessor_status"] = f"INTEGRITY_ERROR: {exc}"
                except Exception as exc:
                    record["assessor_status"] = f"ERROR: {type(exc).__name__}: {exc}"

            # 2. Pull Recorder Data (if doc number is found or via recorder search)
            if recorder and doc_number_found:
                try:
                    mt = search_document_with_variants(recorder, doc_number_found)
                    if mt.events:
                        tally["recorder_hits"] += 1
                        record["recorder_status"] = "OK"
                        record["recorder_event"] = mt.events[0].model_dump(mode="json")
                        record["variant_matched"] = mt.variant_matched
                    else:
                        record["recorder_status"] = "NO_HIT"
                except Exception as exc:
                    record["recorder_status"] = f"ERROR: {exc}"

            fh.write(json.dumps(record) + "\n")
            fh.flush()

            # Session refresh every 20 parcels if supported
            if i % 20 == 0 and recorder and hasattr(recorder, "_ensure_session"):
                recorder._ensure_session(force=True)

            if args.progress_every and i % args.progress_every == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                rem_s = (len(master_parcels) - i) / rate if rate > 0 else 0
                print(f"[progress] {i}/{len(master_parcels)} done | "
                      f"assessor_hits={tally['assessor_hits']} recorder_hits={tally['recorder_hits']} | "
                      f"rate={rate:.2f}/s | ETA={rem_s/60:.1f}min")

            time.sleep(args.delay)

    http.close()
    print(f"\n=== SWEEP COMPLETED FOR {county_key.upper()} ===")
    print(f"Total Processed: {len(master_parcels)}")
    print(f"Assessor Hits:   {tally['assessor_hits']}")
    print(f"Recorder Hits:   {tally['recorder_hits']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
