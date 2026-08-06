"""
core/recorder.py

Unified recorder/index connector. The Tyler backend wraps the shared
tyler_recorder_client (Tehama/Shasta/Butte/Fresno all proven). One
interface so the pipeline treats every county's recorder the same way.

Stage produces the standard recorder_docs.csv:
    county, apn, doc_id, doc_number, doc_type, recording_date,
    grantors, grantees
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .county import CountyConfig


def pull_recorder_for_doc_numbers(cfg: CountyConfig,
                                  apn_doc: list[tuple[str, str]],
                                  out_path: Path | None = None) -> Path:
    """Search the recorder by document number (counties whose recorder has
    no APN index, e.g. Tehama). Each doc search returns the deed's parties
    and type — mapped back to the parcel via the doc number the assessor
    roll gave us. Same output schema as pull_recorder_for_apns."""
    out_path = out_path or cfg.recorder_path()
    backend = cfg.recorder.backend
    if backend != "tyler":
        raise ValueError(f"Recorder backend not implemented: {backend}")

    from tyler_recorder_client import TylerRecorderClient, CountyConfig as TylerCC

    tcfg = TylerCC(
        county=cfg.county,
        base_url=cfg.recorder.base_url,
        name_search_id=cfg.recorder.name_search_id,
        doc_search_id=cfg.recorder.doc_search_id,
        apn_search_id=cfg.recorder.apn_search_id or "",
        ajax_headers_required=cfg.recorder.ajax_headers_required,
        doc_number_transform=cfg.recorder.doc_number_transform,
        doc_field_name=cfg.recorder.doc_field or "field_DocumentNumberID",
    )

    client = TylerRecorderClient(tcfg)
    rows = []
    try:
        for i, (apn, doc) in enumerate(apn_doc, 1):
            try:
                post = client.submit_doc_search(doc)
                import json as _json
                try:
                    total_pages = int(_json.loads(post.text).get("totalPages", 0))
                except Exception:
                    total_pages = 0
                results = []
                for page in range(1, max(total_pages, 1) + 1):
                    pr, _ = client.get_results(page=page, search_type="doc")
                    results.extend(pr)
                    if page < total_pages:
                        import time
                        time.sleep(0.5)
                for r in results:
                    rows.append({
                        "county": cfg.county, "apn": apn,
                        "doc_id": r.doc_id, "doc_number": r.doc_number,
                        "doc_type": r.doc_type, "recording_date": r.recording_date,
                        "grantors": " | ".join(r.grantors),
                        "grantees": " | ".join(r.grantees),
                    })
                print(f"[recorder:{cfg.county}] {apn} ({doc}): {len(results)} docs", flush=True)
            except Exception as e:
                print(f"[recorder:{cfg.county}] {apn} FAILED: {str(e)[:120]}")
            import time
            time.sleep(0.8)
    finally:
        client.close()

    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=[
            "county", "apn", "doc_id", "doc_number", "doc_type",
            "recording_date", "grantors", "grantees"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[recorder:{cfg.county}] wrote {len(rows)} docs -> {out_path}")
    return out_path


def pull_recorder_for_apns(cfg: CountyConfig, apns: list[str],
                           out_path: Path | None = None) -> Path:
    out_path = out_path or cfg.recorder_path()
    backend = cfg.recorder.backend
    if backend != "tyler":
        raise ValueError(f"Recorder backend not implemented: {backend}")

    from tyler_recorder_client import TylerRecorderClient, CountyConfig as TylerCC

    tcfg = TylerCC(
        county=cfg.county,
        base_url=cfg.recorder.base_url,
        name_search_id=cfg.recorder.name_search_id,
        doc_search_id=cfg.recorder.doc_search_id,
        apn_search_id=cfg.recorder.apn_search_id or "",
        ajax_headers_required=cfg.recorder.ajax_headers_required,
        doc_number_transform=cfg.recorder.doc_number_transform,
        doc_field_name=cfg.recorder.doc_field or "field_DocumentNumberID",
    )

    client = TylerRecorderClient(tcfg)
    rows = []
    try:
        for i, apn in enumerate(apns, 1):
            try:
                post = client.submit_apn_search(apn) if tcfg.apn_search_id else client.submit_name_search(apn)
                import json as _json
                try:
                    total_pages = int(_json.loads(post.text).get("totalPages", 0))
                except Exception:
                    total_pages = 0
                results = []
                for page in range(1, max(total_pages, 1) + 1):
                    pr, _ = client.get_results(page=page, search_type="apn" if tcfg.apn_search_id else "name")
                    results.extend(pr)
                    if page < total_pages:
                        import time
                        time.sleep(0.5)
                for r in results:
                    rows.append({
                        "county": cfg.county, "apn": apn,
                        "doc_id": r.doc_id, "doc_number": r.doc_number,
                        "doc_type": r.doc_type, "recording_date": r.recording_date,
                        "grantors": " | ".join(r.grantors),
                        "grantees": " | ".join(r.grantees),
                    })
                print(f"[recorder:{cfg.county}] {apn}: {len(results)} docs", flush=True)
            except Exception as e:
                print(f"[recorder:{cfg.county}] {apn} FAILED: {str(e)[:120]}")
            import time
            time.sleep(0.8)
    finally:
        client.close()

    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=[
            "county", "apn", "doc_id", "doc_number", "doc_type",
            "recording_date", "grantors", "grantees"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[recorder:{cfg.county}] wrote {len(rows)} docs -> {out_path}")
    return out_path
