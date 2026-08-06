"""
run.py — unified CLI runner for county pipeline adapters.

Usage:
  python run.py --county tehama --source recorder --doc 2026R006490
  python run.py --county tehama --source assessor --apn 004-110-034-000
  python run.py --county shasta --source assessor --apn 001-100-001-000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from contracts import SourceType, build_adapters_for_county
from county_config_loader import load_county_config
from http_client import build_http_client
from multi_transform import search_document_with_variants
from normalizers import DefaultNormalizers
from raw_store import FileRawStore

# Ensure all registered adapters are imported
import arcgis_assessor  # noqa: F401
import mpts_assessor  # noqa: F401
import tehama_recorder_tyler  # noqa: F401


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified County Pipeline Runner")
    parser.add_argument("--county", type=str, required=True, help="County key (e.g. tehama, shasta, butte)")
    parser.add_argument("--source", type=str, choices=["recorder", "assessor"], default="recorder", help="Source type")
    parser.add_argument("--doc", type=str, help="Document number for recorder search")
    parser.add_argument("--apn", type=str, help="APN for assessor or recorder search")
    parser.add_argument("--name", type=str, help="Name for recorder search")
    parser.add_argument("--no-multi-transform", action="store_true", help="Disable doc variant sweep")
    parser.add_argument("--out", type=str, help="Output JSON file path")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent

    try:
        cfg = load_county_config(args.county)
    except Exception as exc:
        print(f"[run] Error loading county config for '{args.county}': {exc}", file=sys.stderr)
        return 1

    norm = DefaultNormalizers(home_county=args.county)
    store = FileRawStore(root_dir=str(root / "data"))
    http = build_http_client()

    try:
        adapters = build_adapters_for_county(cfg, http, store, norm)
    except Exception as exc:
        print(f"[run] Error building adapters for '{args.county}': {exc}", file=sys.stderr)
        http.close()
        return 1

    source_type = SourceType(args.source)
    if source_type not in adapters:
        print(f"[run] Source type '{args.source}' not configured for county '{args.county}'", file=sys.stderr)
        http.close()
        return 1

    adapter = adapters[source_type]
    results = []

    try:
        if source_type == SourceType.RECORDER:
            if args.doc:
                if args.no_multi_transform:
                    events = adapter.search_by_document_number(args.doc)
                else:
                    mt = search_document_with_variants(adapter, args.doc)
                    events = mt.events
                results = [e.model_dump(mode="json") for e in events]
            elif args.name:
                events = adapter.search_by_name(args.name)
                results = [e.model_dump(mode="json") for e in events]
            elif args.apn:
                events = adapter.search_by_apn(args.apn)
                results = [e.model_dump(mode="json") for e in events]
            else:
                print("[run] For recorder source, specify --doc, --name, or --apn", file=sys.stderr)
                http.close()
                return 1

        elif source_type == SourceType.ASSESSOR:
            if args.apn:
                asr_result = adapter.fetch_by_apn(args.apn)
                results = [asr_result.model_dump(mode="json")]
            else:
                print("[run] For assessor source, specify --apn", file=sys.stderr)
                http.close()
                return 1

    except Exception as exc:
        print(f"[run] Execution error: {exc}", file=sys.stderr)
        http.close()
        return 1

    http.close()

    output_data = {
        "county": args.county,
        "source": args.source,
        "count": len(results),
        "results": results,
    }

    formatted_json = json.dumps(output_data, indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(formatted_json, encoding="utf-8")
        print(f"[run] Saved {len(results)} records to {args.out}")
    else:
        print(formatted_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
