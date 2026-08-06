"""
core/pipeline.py

Stage orchestrator. `python pipeline.py --county fresno --stage all` runs
every stage in order; each stage is independently resumable and writes to
the county's standard data dir.

Stages:
  source     pull the full assessor roll at the source (all parcels)
  enrich     fill owner/values/situs/mailing from the assessor source
  recorder   pull recorded deeds/liens per APN (former owners)
  predict    score the full roll for next-auction likelihood (signals)
  auction    poll the auction platform for the live list
  deliver    build dossiers + letters from joined data
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .county import CountyConfig, list_counties


def _apn_of(row: dict, apn_field: str) -> str:
    """Case-insensitive APN extraction across all known field spellings."""
    for f in (apn_field, "APN", "apn", "ASMT", "asmt", "Asmt"):
        v = row.get(f)
        if v:
            return str(v).strip().replace("-", "")
    return ""


def _situs_of(row: dict) -> str:
    """Extract situs/address from any known column spelling."""
    for f in ("Situs_Address", "SITEADDRESS1", "situs", "Situs",
              "address", "Address"):
        v = row.get(f)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def run_stage(cfg: CountyConfig, stage: str, max_passes: int = 50,
              batch: int = 500, blank_policy: str = "self-correct"):
    if stage == "source":
        from .assessor import pull_roll
        return pull_roll(cfg)

    if stage == "enrich":
        # Per-APN enrichment from the assessor backend. For a rich roll this
        # is a no-op (source already has everything); for thin rolls (Shasta
        # = APN+situs only) it fills values/mailing/use for the candidate pool.
        from .assessor import _arcgis_apn_enrich
        from .state import StateStore

        store = StateStore(cfg)
        # Seed the full roll into state if it isn't there yet.
        if store.count() == 0:
            roll = cfg.roll_path()
            if roll.exists():
                import csv
                apn_field = cfg.assessor.apn_field
                n = 0
                with open(roll, newline="", encoding="utf-8-sig") as fp:
                    reader = csv.DictReader(fp)
                    rich_fields = [f for f in ("TOTAL_ASSESSED_VALUE", "NAME1",
                                               "ADDRESS1", "USE_PRIMARY",
                                               "SITEADDRESS1") if f in reader.fieldnames]
                    for row in reader:
                        apn = _apn_of(row, apn_field)
                        if not apn:
                            continue
                        vals = {"situs": _situs_of(row)}
                        store.upsert_parcel(apn, vals, commit=False)
                        if vals["situs"]:
                            store.mark_known(apn, "situs", commit=False)
                        for f, col in (("values", "TOTAL_ASSESSED_VALUE"),
                                       ("mailing", "ADDRESS1"),
                                       ("use", "USE_PRIMARY"),
                                       ("owner", "NAME1")):
                            v = str(row.get(col) or "").strip()
                            if v and v.lower() != "nan":
                                store.upsert_parcel(apn, {f: v}, commit=False)
                                store.mark_known(apn, f, commit=False)
                        n += 1
                        if n % 5000 == 0:
                            store.commit()
                            print(f"  seeded {n:,}...")
                store.commit()
                print(f"[pipeline:{cfg.county}] seeded {n:,} parcels from roll")
            else:
                print("[pipeline] no roll to seed from")

        targets = cfg.data_dir() / "recorder_targets.csv"
        apns = []
        if targets.exists():
            import csv
            with open(targets, newline="", encoding="utf-8-sig") as fp:
                for row in csv.DictReader(fp):
                    a = (row.get("apn") or "").strip()
                    if a:
                        apns.append(a)
        if not apns and cfg.roll_path().exists():
            import csv as _csv
            with open(cfg.roll_path(), newline="", encoding="utf-8-sig") as fp:
                apns = [_apn_of(r, cfg.assessor.apn_field)
                        for r in _csv.DictReader(fp)]
            apns = [a for a in apns if a]
        apns = list(dict.fromkeys(apns))
        print(f"[pipeline:{cfg.county}] enrich {len(apns):,} apns via "
              f"assessor backend '{cfg.assessor.backend}'")

        if cfg.assessor.backend != "arcgis":
            store.close()
            print(f"[pipeline:{cfg.county}] enrich for backend "
                  f"'{cfg.assessor.backend}' not wired yet (arcgis proven)")
            return None

        recs = _arcgis_apn_enrich(cfg, apns)
        updated = 0
        for rec in recs:
            apn = str(rec.get(cfg.assessor.apn_field) or "").strip().replace("-", "")
            if not apn:
                continue
            vals = {
                "values": str(rec.get("TOTAL_ASSESSED_VALUE") or ""),
                "mailing": " ".join(str(rec.get(f) or "") for f in
                                    ("ADDRESS1", "ADDRESS2", "ADDRESS3")),
                "use": str(rec.get("USE_PRIMARY") or ""),
                "situs": str(rec.get("SITEADDRESS1") or rec.get("Situs_Address") or ""),
            }
            store.upsert_parcel(apn, vals, commit=False)
            # Only mark a field known when the source actually returned it —
            # thin layers (e.g. Shasta = APN+situs only) must NOT count
            # values/mailing/use as filled.
            for f, v in vals.items():
                if v and v.strip():
                    store.mark_known(apn, f, commit=False)
            updated += 1
            if updated % 1000 == 0:
                store.commit()
        store.commit()
        store.close()
        print(f"[pipeline:{cfg.county}] enriched {updated:,} parcels "
              f"(fields only marked known when actually returned)")
        return None

    if stage == "recorder":
        from .recorder import pull_recorder_for_apns
        roll = cfg.roll_path()
        # Prefer an explicit candidate list (the counties/*_candidates.csv or
        # predicted top-N) so we never blindly scan the full roll.
        candidates = cfg.data_dir() / "recorder_targets.csv"
        src = candidates if candidates.exists() else roll
        if not src.exists():
            print("[pipeline] run stage source first")
            return None
        import csv
        apns = []
        with open(src, newline="", encoding="utf-8-sig") as fp:
            for row in csv.DictReader(fp):
                apn = _apn_of(row, cfg.assessor.apn_field)
                if apn:
                    apns.append(apn)
        apns = list(dict.fromkeys(apns))
        print(f"[pipeline:{cfg.county}] recorder for {len(apns):,} apns"
              f"{' (candidates)' if src == candidates else ' (FULL ROLL)'}")
        return pull_recorder_for_apns(cfg, apns)

    if stage == "predict":
        from .signals import build_predictions
        return build_predictions(cfg)

    if stage == "auction":
        # The loop's filler owns the state upserts (sold results + listed
        # status); calling it here keeps stage and loop identical.
        from .loop import _fill_auction
        from .state import StateStore
        store = StateStore(cfg)
        try:
            n = _fill_auction(cfg, store, "auction_status", batch, print)
            print(f"[pipeline:{cfg.county}] auction: {n} parcels updated")
        finally:
            store.close()
        return None

    if stage == "deliver":
        from .deliver import deliver
        return deliver(cfg)

    if stage == "import":
        from .ingest import import_recorder_docs
        return import_recorder_docs(cfg)

    if stage == "excess":
        from .excess import excess_report
        return excess_report(cfg)

    if stage == "loop":
        from .loop import run_loop
        from .state import StateStore

        # seed state from the roll if empty
        store = StateStore(cfg)
        if store.count() == 0:
            roll = cfg.roll_path()
            if not roll.exists():
                print("[pipeline] run stage source first")
                return None
            import csv
            apn_field = cfg.assessor.apn_field
            n = 0
            with open(roll, newline="", encoding="utf-8-sig") as fp:
                reader = csv.DictReader(fp)
                # First stop (the roll) already provides these when the
                # source layer is rich — import them so the loop only
                # targets what's genuinely missing.
                rich_fields = [f for f in ("TOTAL_ASSESSED_VALUE", "NAME1",
                                           "ADDRESS1", "USE_PRIMARY",
                                           "SITEADDRESS1") if f in reader.fieldnames]
                for row in reader:
                    apn = _apn_of(row, apn_field)
                    if not apn:
                        continue
                    store.upsert_parcel(apn, {"situs": _situs_of(row)}, commit=False)
                    if _situs_of(row):
                        store.mark_known(apn, "situs", commit=False)
                    for f, col in (("values", "TOTAL_ASSESSED_VALUE"),
                                   ("mailing", "ADDRESS1"),
                                   ("use", "USE_PRIMARY"),
                                   ("owner", "NAME1")):
                        v = str(row.get(col) or "").strip()
                        if v and v.lower() != "nan":
                            store.upsert_parcel(apn, {f: v}, commit=False)
                            store.mark_known(apn, f, commit=False)
                    n += 1
                    if n % 5000 == 0:
                        store.commit()
                        print(f"  seeded {n:,}...")
                store.commit()
            print(f"[pipeline:{cfg.county}] seeded state with {n:,} parcels "
                  f"(rich roll: {bool(rich_fields)})")
        store.close()
        return run_loop(cfg, max_passes=max_passes, batch=batch,
                        blank_policy=blank_policy)

    raise ValueError(f"Unknown stage: {stage}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline.py", description=__doc__)
    ap.add_argument("--county", required=True, choices=list_counties())
    ap.add_argument("--stage", default="all",
                    help="one of source|enrich|recorder|predict|auction|import|excess|loop|deliver, or all")
    ap.add_argument("--blank-policy", default="self-correct",
                    choices=["self-correct", "restart", "stop"],
                    help="loop integrity behavior on blank spots: self-correct (re-pull, halt if impossible), restart (re-pull later), or stop (halt)")
    ap.add_argument("--max-passes", type=int, default=50,
                    help="loop max passes (each pass fills one gap field)")
    ap.add_argument("--batch", type=int, default=500,
                    help="loop batch size per recorder/assessor pass")
    args = ap.parse_args(argv)

    cfg = CountyConfig.load(args.county)
    stages = ["source", "enrich", "recorder", "predict", "auction",
              "import", "excess", "loop", "deliver"]
    todo = stages if args.stage == "all" else [args.stage]
    for s in todo:
        print(f"\n===== STAGE {s} ({cfg.county}) =====")
        run_stage(cfg, s, max_passes=args.max_passes, batch=args.batch,
                  blank_policy=args.blank_policy)
    print(f"\n[pipeline:{cfg.county}] done. outputs in {cfg.data_dir()}")


if __name__ == "__main__":
    main()
