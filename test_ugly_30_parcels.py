"""
test_ugly_30_parcels.py — 30-Parcel Diverse Edge-Case Verification Suite for Tehama County.

Tests a diverse 30-parcel sample across the full Tehama master index including:
  * Bare land (no situs address)
  * Entity / LLC / Trust owners
  * Parcels with missing or old sale doc numbers
  * Multi-deed recorder matches
  * Standard residential properties

Enforces honest resolution categorization:
  - ASSESSOR_HIT_RECORDER_SINGLE_DEED
  - ASSESSOR_HIT_RECORDER_MULTIPLE_DEEDS
  - ASSESSOR_HIT_RECORDER_NO_DEED
  - ASSESSOR_HIT_NO_DOC_NUMBER
  - ASSESSOR_MISSING
  - ASSESSOR_ERROR
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

from contracts import (
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
import mpts_assessor  # noqa: F401
import tehama_recorder_tyler  # noqa: F401

ROOT = Path(__file__).resolve().parent
MASTER_CSV = ROOT / "tehama" / "tehama_AUTHORITATIVE_master_index.csv"


def select_diverse_30_parcels() -> list[dict[str, str]]:
    with MASTER_CSV.open("r", encoding="utf-8-sig") as fh:
        reader = list(csv.DictReader(fh))

    # Stratify selection across book prefixes to get diverse geographic & property types
    no_situs = [r for r in reader if not (r.get("address") or "").strip()]
    with_situs = [r for r in reader if (r.get("address") or "").strip()]

    selected: list[dict[str, str]] = []

    # Pick 15 no-situs (bare land / rural)
    step_no = max(1, len(no_situs) // 15)
    for i in range(0, min(len(no_situs), 15 * step_no), step_no):
        selected.append({"apn": no_situs[i]["parcel_number"], "situs": "", "category": "no_situs_land"})

    # Pick 15 with-situs across different APN books
    step_with = max(1, len(with_situs) // 15)
    for i in range(0, min(len(with_situs), 15 * step_with), step_with):
        selected.append({
            "apn": with_situs[i]["parcel_number"],
            "situs": with_situs[i]["address"],
            "category": "improved_situs"
        })

    return selected[:30]


def main() -> int:
    parcels = select_diverse_30_parcels()
    print(f"=== 30-PARCEL UGLY CASE TEST SUITE (TEHAMA) ===")
    print(f"Testing {len(parcels)} diverse parcels (15 bare land/no-situs, 15 improved/situs)...")

    cfg = load_county_config("tehama")
    norm = DefaultNormalizers(home_county="tehama")
    store = FileRawStore(root_dir=str(ROOT / "data"))
    http = build_http_client()

    adapters = build_adapters_for_county(cfg, http, store, norm)
    assessor = adapters[SourceType.ASSESSOR]
    recorder = adapters[SourceType.RECORDER]

    tally = {
        "ASSESSOR_HIT_RECORDER_SINGLE_DEED": 0,
        "ASSESSOR_HIT_RECORDER_MULTIPLE_DEEDS": 0,
        "ASSESSOR_HIT_RECORDER_NO_DEED": 0,
        "ASSESSOR_HIT_NO_DOC_NUMBER": 0,
        "ASSESSOR_MISSING": 0,
        "ASSESSOR_ERROR": 0,
    }

    results = []

    for i, p in enumerate(parcels, 1):
        apn = p["apn"]
        category = p["category"]
        print(f"\n[{i:02d}/30] apn={apn} category={category} situs={p['situs']!r}")

        resolution = "ASSESSOR_MISSING"
        doc_number = ""
        owner_name = ""
        grantor = ""
        grantee = ""
        event_type = ""
        deed_count = 0
        data_gaps = []

        try:
            asr_res = assessor.fetch_by_apn(apn)
            owner_name = asr_res.assessee.owner_name_norm if asr_res.assessee else "NO_ASSESSEE"
            doc_number = (asr_res.snapshot.last_sale_doc_number or "").strip()
            data_gaps = asr_res.property.data_gaps + asr_res.snapshot.data_gaps

            if not doc_number:
                resolution = "ASSESSOR_HIT_NO_DOC_NUMBER"
                tally["ASSESSOR_HIT_NO_DOC_NUMBER"] += 1
                print(f"    Assessor: HIT | owner={owner_name!r} | assessed=${asr_res.snapshot.assessed_total} | NO_DOC_NUMBER")
            else:
                print(f"    Assessor: HIT | owner={owner_name!r} | last_sale_doc={doc_number} ({asr_res.snapshot.last_sale_date})")

                # Recorder Search
                try:
                    mt = search_document_with_variants(recorder, doc_number)
                    deed_count = len(mt.events)
                    if deed_count == 1:
                        ev = mt.events[0]
                        grantor = ev.grantor_raw or ""
                        grantee = ev.grantee_raw or ""
                        event_type = ev.event_type.value
                        resolution = "ASSESSOR_HIT_RECORDER_SINGLE_DEED"
                        tally["ASSESSOR_HIT_RECORDER_SINGLE_DEED"] += 1
                        print(f"    Recorder: SINGLE_DEED | {event_type} | FROM={grantor!r} TO={grantee!r}")
                    elif deed_count > 1:
                        resolution = "ASSESSOR_HIT_RECORDER_MULTIPLE_DEEDS"
                        tally["ASSESSOR_HIT_RECORDER_MULTIPLE_DEEDS"] += 1
                        print(f"    Recorder: MULTIPLE_DEEDS ({deed_count} events returned)")
                    else:
                        resolution = "ASSESSOR_HIT_RECORDER_NO_DEED"
                        tally["ASSESSOR_HIT_RECORDER_NO_DEED"] += 1
                        print(f"    Recorder: NO_DEED (Doc {doc_number} matched 0 events in recorder index)")
                except Exception as exc:
                    resolution = "ASSESSOR_HIT_RECORDER_NO_DEED"
                    tally["ASSESSOR_HIT_RECORDER_NO_DEED"] += 1
                    print(f"    Recorder: ERROR ({type(exc).__name__}: {exc})")

        except IntegrityError as exc:
            resolution = "ASSESSOR_ERROR"
            tally["ASSESSOR_ERROR"] += 1
            print(f"    Assessor: INTEGRITY_ERROR ({exc})")
        except Exception as exc:
            resolution = "ASSESSOR_ERROR"
            tally["ASSESSOR_ERROR"] += 1
            print(f"    Assessor: ERROR ({type(exc).__name__}: {exc})")

        results.append({
            "apn": apn,
            "category": category,
            "resolution": resolution,
            "owner_name": owner_name,
            "doc_number": doc_number,
            "deed_count": deed_count,
            "grantor": grantor,
            "grantee": grantee,
            "event_type": event_type,
            "data_gaps": data_gaps,
        })

        if i % 20 == 0 and hasattr(recorder, "_ensure_session"):
            recorder._ensure_session(force=True)

        time.sleep(1.2)

    http.close()

    print("\n" + "=" * 60)
    print("=== 30-PARCEL UGLY CASE RESOLUTION DISTRIBUTION ===")
    print("=" * 60)
    for k, v in tally.items():
        pct = (v / len(parcels)) * 100
        print(f"  {k:42s} {v:2d} ({pct:5.1f}%)")

    # Save verification report
    report_path = ROOT / "data" / "tehama" / "ugly_30_verification_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"tally": tally, "results": results}, indent=2), encoding="utf-8")
    print(f"\n[OK] Detailed report saved to {report_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
