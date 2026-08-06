"""
core/deliver.py

Unified delivery: consume the county state store and produce the
lead-agent package for whatever parcels are flagged (tax deeds, predicted
auction list, etc.).

Outputs into the county's data dir:
    delivery_summary.csv   one row per target parcel, all known fields
    delivery_callsheet.xlsx (if openpyxl available) — sortable workbook
    delivery_log.txt        run record

The Butte reference (butte/build_dossiers.py) is the full branded-PDF
path; this is the data-first deliverable that works for every county.
"""
import csv
import datetime as dt
from pathlib import Path

from .county import CountyConfig
from .state import StateStore


def deliver(cfg: CountyConfig, score_floor: int = 50) -> Path:
    store = StateStore(cfg)
    out = cfg.data_dir() / "delivery_summary.csv"
    log = cfg.data_dir() / "delivery_log.txt"

    rows = []
    cur = store.conn.cursor()
    cols = ["apn", "owner", "former_owner", "tax_deed", "values", "situs",
            "mailing", "use", "auction_status"]
    # Universal target signal (works for every county, no auction list
    # required): the county tax collector is a party on the parcel —
    # either it holds the deed now (auction/excess-proceeds candidate) or
    # it formerly held it (recent county sale).
    for r in cur.execute(
            'SELECT apn, owner, former_owner, tax_deed, "values", situs, '
            "mailing, use, auction_status FROM parcels "
            "WHERE tax_deed='yes' OR auction_status='listed' "
            "ORDER BY apn"):
        rec = dict(zip(cols, r))
        rec["county"] = cfg.county
        rec["exported_at"] = dt.datetime.now().isoformat(timespec="seconds")
        rows.append(rec)

    with open(out, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=["county", "apn", "owner",
                                           "former_owner", "tax_deed",
                                           "values", "situs", "mailing",
                                           "use", "auction_status",
                                           "exported_at"])
        w.writeheader()
        w.writerows(rows)

    # Optional xlsx workbook (fall back gracefully when openpyxl missing)
    try:
        import openpyxl  # noqa: F401
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "targets"
        header = list(rows[0].keys()) if rows else ["county", "apn"]
        ws.append(header)
        for r in rows:
            ws.append([r.get(h, "") for h in header])
        xlsx = cfg.data_dir() / "delivery_callsheet.xlsx"
        wb.save(str(xlsx))
        print(f"[deliver:{cfg.county}] xlsx -> {xlsx}")
    except ImportError:
        pass

    with open(log, "a", encoding="utf-8") as fp:
        fp.write(f"{dt.datetime.now().isoformat(timespec='seconds')}  "
                 f"delivered {len(rows)} target parcels\n")

    print(f"[deliver:{cfg.county}] {len(rows)} target parcels -> {out}")
    store.close()
    return out
