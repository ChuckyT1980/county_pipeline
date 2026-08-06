"""
humboldt_bridge.py - targeted Tyler doc-number bridge for doc-bridge
counties (no APN index on the recorder). Resumable: reads parcels missing
owner/tax_deed info from state, resolves each via submit_doc_search, and
imports results back into state every batch_size docs using the same
classification the loop/import stage applies. Long run — log to file.

Usage: python -m core.bridge --county humboldt [--batch 40] [--resume]
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.county import CountyConfig
from core.state import StateStore
from tyler_recorder_client import TylerRecorderClient, CountyConfig as TylerCC


def collect_docs(cfg, store, limit=None):
    """(apn, doc) pairs for parcels that have a doc number but no owner
    resolution yet (owner unknown, or not even checked)."""
    rows = store.conn.execute(
        "SELECT apn, current_doc_number FROM parcels "
        "WHERE length(current_doc_number) > 0 "
        "AND COALESCE(length(owner), 0) = 0 "
        "AND COALESCE(length(former_owner), 0) = 0 "
        "ORDER BY apn").fetchall()
    pairs = [(a, d) for a, d in rows if d.strip()]
    if limit:
        pairs = pairs[:limit]
    return pairs


def run_bridge(cfg, batch=50, limit=None, logfp=None):
    log = (lambda *a, **k: print(*a, flush=True, **k))
    if logfp:
        log = (lambda *a, **k: (
            print(*a, flush=True, **k),
            logfp.write(" ".join(str(x) for x in a) + "\n"), logfp.flush())[0])
    store = StateStore(cfg)
    pairs = collect_docs(cfg, store, limit)
    log(f"[bridge:{cfg.county}] {len(pairs):,} doc-bearing parcels to "
        f"resolve")
    if not pairs:
        store.close()
        return 0

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
    rows_accum = []
    keyed: dict[str, list[dict]] = {}
    total_resolved = 0
    try:
        for i, (apn, doc) in enumerate(pairs, 1):
            try:
                post = client.submit_doc_search(doc)
                try:
                    total_pages = int(json.loads(post.text).get("totalPages", 0))
                except Exception:
                    total_pages = 0
                results = []
                for page in range(1, max(total_pages, 1) + 1):
                    pr, _ = client.get_results(page=page, search_type="doc")
                    results.extend(pr)
                    if page < total_pages:
                        time.sleep(0.5)
                for r in results:
                    row = {
                        "county": cfg.county, "apn": apn,
                        "doc_id": r.doc_id, "doc_number": r.doc_number,
                        "doc_type": r.doc_type,
                        "recording_date": r.recording_date,
                        "grantors": " | ".join(r.grantors),
                        "grantees": " | ".join(r.grantees),
                    }
                    rows_accum.append(row)
                    keyed.setdefault(apn, []).append(row)
                total_resolved += 1 if results else 0
            except Exception as e:
                log(f"[bridge] {apn} FAILED: {str(e)[:120]}")
            time.sleep(0.3)

            if i % batch == 0 or i == len(pairs):
                nok = _import_rows(cfg, store, rows_accum)
                log(f"[bridge] {i}/{len(pairs)} queried; "
                    f"{total_resolved:,} docs found for {nok:,} parcels")
                rows_accum = []
                keyed.clear()
    finally:
        client.close()
        nok = _import_rows(cfg, store, rows_accum)
        if nok:
            log(f"[bridge] final flush: {nok:,} parcels")
        store.close()
    return total_resolved


def _import_rows(cfg, store, rows):
    """Fold accumulated recorder rows into state per-APN (same rules as
    core.ingest.import_recorder_docs). Returns # parcels stamped."""
    parcels: dict[str, dict] = {}
    for row in rows:
        apn = (row.get("apn") or "").strip()
        if not apn:
            continue
        grantors = (row.get("grantors") or "").upper()
        grantees = (row.get("grantees") or "").upper()
        rec_date = (row.get("recording_date") or "").strip()
        is_tax_deed = (
            cfg.is_county_holder(grantors)
            or cfg.is_county_holder(grantees)
            or "POWER TO SELL" in grantors)
        rec = parcels.get(apn, {"tax_deed": "no", "former_owner": "",
                                "owner": "", "deed_date": ""})
        if is_tax_deed:
            rec["tax_deed"] = "yes"
            if cfg.is_county_holder(grantees):
                if grantors:
                    rec["former_owner"] = grantors.split("|")[0]
                if grantees:
                    rec["owner"] = grantees.split("|")[0]
            else:
                if grantees:
                    rec["owner"] = grantees.split("|")[0]
            if rec_date and not rec["deed_date"]:
                rec["deed_date"] = rec_date
        else:
            if not rec["former_owner"] and grantors:
                rec["former_owner"] = grantors.split("|")[0]
            if not rec["owner"] and grantees:
                rec["owner"] = grantees.split("|")[0]
        parcels[apn] = rec

    updated = 0
    for apn, rec in parcels.items():
        store.upsert_parcel(apn, rec, commit=False)
        store.mark_known(apn, "tax_deed", commit=False)
        for f2 in ("former_owner", "owner"):
            if rec.get(f2):
                store.mark_known(apn, f2, commit=False)
        if rec.get("deed_date"):
            store.mark_known(apn, "deed_date", commit=False)
        updated += 1
    store.commit()
    return updated


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bridge")
    ap.add_argument("--county", required=True)
    ap.add_argument("--batch", type=int, default=250)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--log", default=None)
    args = ap.parse_args(argv)
    cfg = CountyConfig.load(args.county)
    logfp = None
    if args.log:
        logfp = open(args.log, "a", encoding="utf-8")
    try:
        n = run_bridge(cfg, batch=args.batch, limit=args.limit, logfp=logfp)
    finally:
        if logfp:
            logfp.close()


if __name__ == "__main__":
    main()