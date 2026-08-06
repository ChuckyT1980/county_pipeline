"""
core/loop.py

Dynamic pipeline: a feedback loop, not a fixed stage list. Each pass:

  1. load state store for the county
  2. gap analysis — what's still missing per parcel, ranked by value
  3. pick the highest-value gap whose source is ready
  4. pull exactly that (recorder / assessor / auction)
  5. update state, log the pass, repeat

Stops when no high-value gaps remain (or budget exhausted). Every source
adapter is a function that fills specific fields; the loop composes them
in whatever order the data demands.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .county import CountyConfig
from .state import StateStore


class LoopError(Exception):
    """Base for pipeline integrity failures that must halt the run."""


class BlankSpotError(LoopError):
    """A field was marked known but its value is empty (writer bug)."""


class FillError(LoopError):
    """A high-value gap could not be filled — the source is not usable."""


def run_loop(cfg: CountyConfig, max_passes: int = 50,
             batch: int = 500, log=None,
             blank_policy: str = "self-correct",
             max_correct_retries: int = 3) -> StateStore:
    """Run the gap-driven loop.

    blank_policy controls what happens when a "blank spot" is found — a
    field marked known whose value is actually empty (a writer bug, not a
    real unknown):
      - "self-correct": (DEFAULT) reset the bad fields to unknown and
          immediately re-pull them from their source, up to
          max_correct_retries times. If the source still cannot produce
          a value, the run HALTS — it will never ship known-but-empty
          data. Fixes what can be fixed, shuts down on what can't.
      - "restart": reset the bad fields to unknown; the loop re-pulls
          them naturally on a later pass (no immediate re-pull).
      - "stop":   halt immediately and report the blank spots so the bug
                  in the writer that created them can be fixed.
    """
    if blank_policy not in ("self-correct", "restart", "stop"):
        raise ValueError(
            f"blank_policy must be 'self-correct', 'restart' or 'stop', "
            f"got {blank_policy!r}")
    if log is None:
        log = lambda *a, **k: print(*a, flush=True, **k)
    store = StateStore(cfg)
    log(f"[loop:{cfg.county}] state has {store.count():,} parcels")

    passes = 0
    while passes < max_passes:
        blanks = store.blank_spots()
        if blanks:
            log(f"[loop:{cfg.county}] INTEGRITY FAILURE: {len(blanks)} blank "
                f"spot(s) (field marked known but empty)")
            if blank_policy == "stop":
                for b in blanks[:20]:
                    log(f"  {b['apn']} {b['field']} marked known but empty")
                log(f"[loop:{cfg.county}] blank_policy='stop' — HALTING.")
                store.close()
                raise BlankSpotError(f"{len(blanks)} blank spot(s) in "
                                     f"{cfg.county}")
            if blank_policy == "restart":
                n = store.repair_blank_spots()
                log(f"[loop:{cfg.county}] blank_policy='restart' — reset "
                    f"{n} to unknown; they will be re-pulled")
            else:
                _self_correct(cfg, store, blanks, batch, max_correct_retries,
                              log)

        action = store.next_action()
        if action is None:
            log(f"[loop:{cfg.county}] no high-value gaps remaining")
            break
        if action["priority"] < 3:
            log(f"[loop:{cfg.county}] remaining gaps are low-value "
                f"({action['field']}: {action['missing']:,} missing) — stopping")
            break
        if action["source"] == "recorder" and not cfg.recorder.apn_search_id:
            # Doc-number-bridge counties (Tehama): the recorder needs the
            # assessor's current_doc_number before it can answer anything.
            # If we haven't swept the roll yet, pivot to the assessor first.
            have_docs = store.count_with_value("current_doc_number")
            if have_docs == 0:
                log(f"[loop:{cfg.county}] no doc numbers yet — sweeping "
                    f"assessor (MPTS) first")
                action = store.next_action(source="assessor")
                if action is None:
                    log(f"[loop:{cfg.county}] no assessor gaps to fill; "
                        f"recorder bridge needs doc numbers")
                    break
            elif store.known_count("values") < action["missing"]:
                # doc numbers exist but assessor sweep is behind; keep
                # sweeping the roll so the bridge has material.
                assessor_action = store.next_action(source="assessor")
                if assessor_action and assessor_action["priority"] >= 3:
                    action = assessor_action
                    log(f"[loop:{cfg.county}] prioritizing assessor sweep "
                        f"({action['field']}) to feed the recorder bridge")
        if action["source"] == "auction" and not cfg.has_auction():
            # County has no real auction backend (GovEase placeholder etc).
            # The auction gap can never fill — don't chase it. Mark every
            # parcel checked so the loop stops offering it as a gap.
            n = store.mark_all_checked("auction_status")
            log(f"[loop:{cfg.county}] no auction backend configured — "
                f"checked auction_status on {n:,} parcels")
            continue

        field = action["field"]
        source = action["source"]
        log(f"[loop:{cfg.county}] PASS {passes+1}: fill '{field}' via {source} "
            f"({action['missing']:,} missing)")

        filled = _run_action(cfg, store, source, field, batch, log)
        store.log_pass(f"{source}/{field}", filled)
        passes += 1
        if filled == 0 and action["priority"] >= 9 and source != "auction":
            # a high-value gap we pulled but couldn't fill is an error:
            # the source returned nothing usable, so do NOT quietly move on.
            store.close()
            raise FillError(f"{source} returned nothing for '{field}' "
                            f"({cfg.county}); aborting run")
        if filled == 0 and source == "auction":
            # auction list not published yet — a legitimate pause, not an
            # error. Stop this run; the daily poll will re-check later.
            log(f"[loop:{cfg.county}] auction list not live — pausing loop")
            break

    log(f"[loop:{cfg.county}] done after {passes} passes")
    log(f"  summary: {store.summary()}")
    store.close()
    return store


def _self_correct(cfg, store, blanks, batch, max_retries, log):
    """Repair blank spots field-by-field: reset, re-pull from the source,
    verify. If a field is still blank after max_retries, HALT — the source
    genuinely cannot answer it and we will not ship empty data."""
    fields = sorted({b["field"] for b in blanks})
    for field in fields:
        n = store.repair_blank_spots(field)
        source = store.field_source(field)
        log(f"[loop:{cfg.county}] self-correct: reset {n} '{field}' to "
            f"unknown, re-pulling via {source}")
        for attempt in range(1, max_retries + 1):
            filled = _run_action(cfg, store, source, field, batch, log)
            remaining = store.blank_spots(field)
            if not remaining:
                log(f"[loop:{cfg.county}] self-correct: '{field}' repaired "
                    f"({filled} pulled, no blank spots left)")
                break
            log(f"[loop:{cfg.county}] self-correct: '{field}' still has "
                f"{len(remaining)} blank spot(s) after attempt {attempt}"
                f"/{max_retries}")
        else:
            store.close()
            raise BlankSpotError(
                f"self-correct failed for '{field}' in {cfg.county}: "
                f"source '{source}' could not produce a value after "
                f"{max_retries} attempts ({len(remaining)} blank spots); "
                f"halting instead of shipping empty data")


def _run_action(cfg, store, source, field, batch, log):
    if source == "recorder":
        return _fill_recorder(cfg, store, field, batch, log)
    if source == "assessor":
        return _fill_assessor(cfg, store, field, batch, log)
    if source == "auction":
        return _fill_auction(cfg, store, field, batch, log)
    return 0


def _fill_recorder(cfg, store, field, batch, log):
    """Pull recorder docs for APNs missing this field; mark known.
    Zero-doc APNs are a true answer for tax_deed ('no', known). For
    owner/former_owner a zero-doc pull means the recorder has nothing —
    that is marked checked (source asked, nothing exists), never
    known-but-empty. Returns how many APNs were resolved (answered or
    checked)."""
    from .recorder import pull_recorder_for_apns, pull_recorder_for_doc_numbers
    apns = store.apns_missing(field, limit=batch)
    if not apns:
        return 0
    if cfg.recorder.apn_search_id:
        out = pull_recorder_for_apns(cfg, apns)
    else:
        # No APN index on the recorder (Tehama). Bridge through the
        # assessor's current doc number: MPTS AsrPrint gives the doc, the
        # doc search gives the deed's parties. Skip APNs we have no doc
        # for — those can't be answered by the recorder and get checked.
        cur = store.conn.cursor()
        pairs = []
        doc_map = {}
        for apn in apns:
            row = cur.execute(
                'SELECT current_doc_number FROM parcels WHERE apn=?',
                (apn,)).fetchone()
            doc = (row[0] if row else "") or ""
            if doc:
                pairs.append((apn, doc))
                doc_map[apn] = doc
        no_doc = [a for a in apns if a not in doc_map]
        if no_doc:
            store.mark_all_checked_for("owner", no_doc)
        if not pairs:
            log(f"[loop:{cfg.county}] no assessor doc numbers yet for "
                f"'{field}' — run the MPTS assessor sweep first")
            return len(no_doc) or 0
        out = pull_recorder_for_doc_numbers(cfg, pairs)
    import csv
    found = {}
    with open(out, newline="", encoding="utf-8-sig") as fp:
        for row in csv.DictReader(fp):
            apn = (row.get("apn") or "").strip()
            if not apn:
                continue
            grantors = (row.get("grantors") or "").upper()
            grantees = (row.get("grantees") or "").upper()
            dtype = (row.get("doc_type") or "").strip().upper()
            rec_date = (row.get("recording_date") or "").strip()
            # UNIVERSAL SIGNAL: collector as party = tax deed, no doc-type
            # gate (Fresno tax deeds arrive as both "T" and "C" types).
            is_tax_deed = (
                cfg.is_county_holder(grantors)
                or cfg.is_county_holder(grantees)
                or "POWER TO SELL" in grantors)
            rec = found.get(apn, {"tax_deed": "no", "former_owner": "",
                                  "owner": "", "deed_date": ""})
            if is_tax_deed:
                rec["tax_deed"] = "yes"
                if cfg.is_county_holder(grantees):
                    # county took title: grantor is the true former owner.
                    if grantors:
                        rec["former_owner"] = grantors.split("|")[0]
                    if grantees:
                        rec["owner"] = grantees.split("|")[0]
                else:
                    # county sold (or power-to-sell): buyer is current
                    # owner; never let the county clobber former_owner —
                    # that person holds the excess-proceeds claim.
                    if grantees:
                        rec["owner"] = grantees.split("|")[0]
                if rec_date and not rec["deed_date"]:
                    rec["deed_date"] = rec_date
            else:
                if not rec["former_owner"] and grantors:
                    rec["former_owner"] = grantors.split("|")[0]
                if not rec["owner"] and grantees:
                    rec["owner"] = grantees.split("|")[0]
            found[apn] = rec
    resolved = 0
    for apn in apns:
        rec = found.get(apn)
        if rec:
            store.upsert_parcel(apn, rec)
            store.mark_known(apn, "tax_deed")
            for f2, v in (("former_owner", rec["former_owner"]),
                          ("owner", rec["owner"]),
                          ("deed_date", rec["deed_date"])):
                if v and v.lower() != "nan":
                    store.mark_known(apn, f2)
                elif f2 != "deed_date":
                    store.mark_checked(apn, f2)
            resolved += 1
        else:
            # no recorded docs at all = honest 'no tax deed'; the recorder
            # cannot answer owner/former_owner, so mark those checked.
            store.upsert_parcel(apn, {"tax_deed": "no"})
            store.mark_known(apn, "tax_deed")
            store.mark_checked(apn, "owner")
            store.mark_checked(apn, "former_owner")
            resolved += 1
    log(f"[loop:{cfg.county}] recorder: {resolved}/{len(apns)} parcels "
        f"resolved for '{field}' ({store.known_count('tax_deed')} total "
        f"tax-deed-flagged)")
    return resolved


def _fill_assessor(cfg, store, field, batch, log):
    """Enrich values/situs/mailing/use via the assessor backend.
    Only marks a field known when a non-empty value actually landed —
    never known-but-empty."""
    apns = store.apns_missing(field, limit=batch)
    if not apns:
        return 0
    if cfg.recorder.apn_search_id:
        # Recorder has a direct APN index (Fresno): assessor enrich per
        # configured backend.
        if cfg.assessor.backend == "arcgis":
            from .assessor import _arcgis_apn_enrich
            records = _arcgis_apn_enrich(cfg, apns)
        elif cfg.assessor.backend == "mpts":
            from .assessor import _mpts_apn_enrich
            records = _mpts_apn_enrich(cfg, apns)
        else:
            log(f"[loop:{cfg.county}] assessor backend {cfg.assessor.backend} "
                f"not wired for per-APN enrich yet")
            return 0
    else:
        # Doc-number-bridge county (Butte/Shasta/Tehama): the assessor's
        # job here is to yield the current document number via MPTS, which
        # the recorder bridge then resolves. MPTS serves the tax-bill
        # (Butte/Shasta) and AsrPrint (Tehama) pages alike.
        from .assessor import _mpts_apn_enrich
        records = _mpts_apn_enrich(cfg, apns)
    updated = 0
    for rec in records:
        apn = rec.get("APN") or rec.get("ASMT") or ""
        if not apn:
            continue
        vals = {
            "values": str(rec.get("TOTAL_ASSESSED_VALUE") or "").strip(),
            "situs": str(rec.get("SITEADDRESS1") or rec.get("Situs_Address")
                         or "").strip(),
            "mailing": " ".join(str(rec.get(f) or "") for f in
                                ("ADDRESS1", "ADDRESS2", "ADDRESS3")).strip(),
            "use": str(rec.get("USE_PRIMARY") or "").strip(),
            "acreage": str(rec.get("ACREAGE") or "").strip(),
            "current_doc_number": str(rec.get("CURRENT_DOC_NUMBER") or "").strip(),
        }
        if any(vals.values()):
            store.upsert_parcel(apn, vals)
        for f2, v in vals.items():
            if v and v.lower() != "nan":
                store.mark_known(apn, f2)
        updated += 1
    return updated


def _fill_auction(cfg, store, field, batch, log):
    """Poll auction platform; mark every listed APN. Also imports the
    county's published sold-results list (min_bid / sold price / excess
    proceeds) when present — the excess-proceeds track."""
    from .auction import poll_preview, import_sold_results
    import csv

    sold_path = cfg.data_dir() / "sold_results.csv"
    if sold_path.exists():
        out = import_sold_results(cfg)
        n = 0
        with open(out, newline="", encoding="utf-8-sig") as fp:
            for row in csv.DictReader(fp):
                apn = (row.get("apn") or "").strip()
                if not apn:
                    continue
                vals = {}
                for f2, col in (("auction_min_bid", "min_bid"),
                                ("auction_sold_price", "sales_price"),
                                ("auction_excess_proceeds", "excess_proceeds")):
                    v = (row.get(col) or "").strip()
                    if v:
                        vals[f2] = v
                if vals:
                    store.upsert_parcel(apn, vals)
                    for f2 in vals:
                        store.mark_known(apn, f2)
                    n += 1
        log(f"[loop:{cfg.county}] auction: sold results imported for "
            f"{n} parcels")
        return n

    out = poll_preview(cfg)
    apns = []
    with open(out, newline="", encoding="utf-8-sig") as fp:
        for row in csv.DictReader(fp):
            apn = (row.get("apn") or "").strip()
            if apn:
                apns.append(apn)
    for apn in apns:
        store.upsert_parcel(apn, {"auction_status": "listed"})
        store.mark_known(apn, "auction_status")
    log(f"[loop:{cfg.county}] auction: {len(apns)} parcels listed")
    return len(apns)
