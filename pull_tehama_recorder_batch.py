"""
pull_tehama_recorder_batch.py — first real production pull through the
unified contract.

Reads doc_numbers from data/tehama/tehama_owner_enriched.csv (the v1
enricher output), runs each through the unified TehamaTylerRecorderAdapter,
and writes canonical Event records to data/tehama/unified_pull_YYYY-MM-DD.jsonl.

Compares each result to what the v1 direct-scraper enricher captured. Any
divergence is either a wire regression (bad) or a new match v1 missed (good).

Batch size defaults to 10 so the network footprint stays small on the first
production run. Bump --limit deliberately once you're satisfied with parity.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

from contracts import (
    CountyConfig,
    IntegrityError,
    SourceConfig,
    SourceType,
    build_adapters_for_county,
)
from http_client import build_http_client
from multi_transform import search_document_with_variants
from normalizers import DefaultNormalizers
from raw_store import FileRawStore
import tehama_recorder_tyler  # noqa: F401 — registers the adapter


ROOT = Path(__file__).resolve().parent
ENRICHED_CSV = ROOT / "data" / "tehama" / "tehama_owner_enriched.csv"


def load_candidates(limit: int) -> list[dict]:
    """Return top-N Tehama rows that have a doc_number, sorted by signal_score."""
    with ENRICHED_CSV.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with_doc = [r for r in rows if (r.get("doc_number") or "").strip()]
    with_doc.sort(key=lambda r: float(r.get("signal_score") or 0), reverse=True)
    return with_doc[:limit] if limit > 0 else with_doc


def load_already_processed(out_path: Path) -> set[str]:
    """Return APNs already in the JSONL — used to resume mid-sweep after a
    crash or a deliberate stop. Silently returns empty on fresh runs."""
    processed: set[str] = set()
    if not out_path.exists():
        return processed
    with out_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            apn = row.get("apn")
            if apn:
                processed.add(apn)
    return processed


def compare_to_v1(unified_grantee: str | None, v1_owner: str) -> str:
    """Classify how the unified result compares to what v1 captured."""
    v1_owner = (v1_owner or "").strip()
    unified_grantee = (unified_grantee or "").strip()
    if unified_grantee and v1_owner:
        # v1 stores only the first grantee; unified joins them with '; '.
        first_unified = unified_grantee.split(";")[0].strip()
        return "match" if first_unified.upper() == v1_owner.upper() else "differ"
    if unified_grantee and not v1_owner:
        return "unified_only"
    if v1_owner and not unified_grantee:
        return "v1_only"
    return "both_empty"


def main() -> int:
    ap = argparse.ArgumentParser(description="First real production pull through the unified contract.")
    ap.add_argument("--limit", type=int, default=10,
                    help="how many top-scored APNs to pull (default 10; pass 0 for ALL)")
    ap.add_argument("--out", type=str, default="",
                    help="output JSONL path (default: data/tehama/unified_pull_YYYY-MM-DD.jsonl)")
    ap.add_argument("--no-multi-transform", action="store_true",
                    help="disable the multi-transform variant sweep (use raw doc only)")
    ap.add_argument("--resume", action="store_true",
                    help="append to --out and skip APNs already present (crash-safe resume)")
    ap.add_argument("--progress-every", type=int, default=25,
                    help="print a rolling tally every N parcels (default 25)")
    args = ap.parse_args()

    candidates = load_candidates(args.limit)
    if not candidates:
        print("[pull] no candidates with doc_numbers — is tehama_owner_enriched.csv present?")
        return 1

    out_path = Path(args.out) if args.out else (
        ROOT / "data" / "tehama" / f"unified_pull_{date.today().isoformat()}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    processed: set[str] = set()
    file_mode = "w"
    if args.resume:
        processed = load_already_processed(out_path)
        file_mode = "a"
        if processed:
            candidates = [r for r in candidates if r["apn"] not in processed]
            print(f"[pull] resume: {len(processed)} APNs already processed; "
                  f"{len(candidates)} remaining")

    norm = DefaultNormalizers(home_county="tehama")
    store = FileRawStore(root_dir=str(ROOT / "data"))
    http = build_http_client()

    cfg = CountyConfig(
        key="tehama",
        display_name="Tehama County",
        sources={
            SourceType.RECORDER: SourceConfig(
                vendor="tyler",
                url="https://recordsearch.tehama.gov",
                method="html",
                parser_version="2024.1.40-tehama-1",
            ),
        },
    )
    adapters = build_adapters_for_county(cfg, http, store, norm)
    recorder = adapters[SourceType.RECORDER]

    print(f"[pull] pulling {len(candidates)} tehama parcels via unified contract")
    print(f"[pull] output: {out_path.relative_to(ROOT)}")

    tally = {"match": 0, "differ": 0, "unified_only": 0, "v1_only": 0,
             "both_empty": 0, "no_hit": 0, "integrity_error": 0, "other_error": 0}

    start_time = time.time()
    with out_path.open(file_mode, encoding="utf-8") as fh:
        for i, row in enumerate(candidates, 1):
            apn = row["apn"]
            doc = row["doc_number"].strip()
            v1_owner = row.get("verified_current_owner_name", "").strip()
            v1_status = row.get("owner_lookup_status", "")

            print(f"\n[{i}/{len(candidates)}] apn={apn} doc={doc}")
            print(f"    v1: {v1_status!r} owner={v1_owner!r}")

            variant_matched = ""
            variants_tried = 1
            integrity_msg = ""
            try:
                if args.no_multi_transform:
                    events = list(recorder.search_by_document_number(doc))
                else:
                    mt = search_document_with_variants(recorder, doc)
                    events = list(mt.events)
                    variant_matched = mt.variant_matched
                    variants_tried = mt.tried
                    integrity_msg = mt.integrity_error
            except IntegrityError as exc:
                print(f"    UNIFIED integrity gate: {exc}")
                tally["integrity_error"] += 1
                fh.write(json.dumps({
                    "apn": apn, "doc": doc, "status": "integrity_error",
                    "error": str(exc), "v1_status": v1_status, "v1_owner": v1_owner,
                }) + "\n")
                continue
            except Exception as exc:
                print(f"    UNIFIED error: {type(exc).__name__}: {str(exc)[:120]}")
                tally["other_error"] += 1
                fh.write(json.dumps({
                    "apn": apn, "doc": doc, "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "v1_status": v1_status, "v1_owner": v1_owner,
                }) + "\n")
                continue

            if not events:
                gate_note = f" (last integrity gate: {integrity_msg[:80]})" if integrity_msg else ""
                print(f"    UNIFIED: no results after {variants_tried} variant(s){gate_note}")
                tally["no_hit"] += 1
                fh.write(json.dumps({
                    "apn": apn, "doc": doc, "status": "no_hit",
                    "variants_tried": variants_tried,
                    "integrity_error": integrity_msg,
                    "v1_status": v1_status, "v1_owner": v1_owner,
                }) + "\n")
                continue

            ev = events[0]
            cls = compare_to_v1(ev.grantee_raw, v1_owner)
            tally[cls] += 1
            variant_note = f" (variant={variant_matched!r} of {variants_tried} tried)" if variant_matched and variant_matched != doc else ""
            print(f"    UNIFIED: {ev.event_type.value} | grantor={ev.grantor_raw!r} | grantee={ev.grantee_raw!r}{variant_note}")
            print(f"    vs v1: {cls}")

            fh.write(json.dumps({
                "apn": apn,
                "doc": doc,
                "status": "hit",
                "variant_matched": variant_matched,
                "variants_tried": variants_tried,
                "comparison": cls,
                "v1_status": v1_status,
                "v1_owner": v1_owner,
                "unified_event": ev.model_dump(mode="json"),
            }) + "\n")

            # Flush per parcel so a mid-sweep crash loses at most one row.
            fh.flush()

            # Proactive session refresh every 20 parcels to prevent session wedging
            if i % 20 == 0 and hasattr(recorder, "_ensure_session"):
                print("    [session] proactive session refresh (every 20 parcels)...")
                recorder._ensure_session(force=True)
                time.sleep(1.0)

            # Rolling tally so long runs are observable without tailing the file.
            if args.progress_every and i % args.progress_every == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (len(candidates) - i) / rate if rate > 0 else 0
                hits = tally["match"] + tally["differ"] + tally["unified_only"]
                print(f"\n[progress] {i}/{len(candidates)} done  "
                      f"hits={hits} no_hit={tally['no_hit']} err={tally['integrity_error']+tally['other_error']}  "
                      f"rate={rate:.2f}/s  eta={remaining/60:.1f}min\n")

            # Politeness pause between parcels
            time.sleep(1.5)

    http.close()

    print("\n=== TALLY ===")
    for k, v in tally.items():
        print(f"  {k:20s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
