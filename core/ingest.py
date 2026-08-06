"""
core/import.py

Fold any standard pipeline output CSV back into the county state store.
Used after long background runs (recorder pools, etc.) so the dynamic
loop sees the updated gaps without re-pulling anything.
"""
import csv
from pathlib import Path

from .county import CountyConfig
from .state import StateStore


def import_recorder_docs(cfg: CountyConfig, path: Path | None = None,
                         store: StateStore | None = None) -> dict:
    """Import recorder_docs.csv; mark tax_deed / former_owner / owner known
    per parcel. Returns per-field counts."""
    path = path or cfg.recorder_path()
    own_store = store is None
    if own_store:
        store = StateStore(cfg)
    if not path.exists():
        print(f"[import:{cfg.county}] no recorder file at {path}")
        return {}

    counts = {"tax_deed": 0, "parcels_updated": 0}
    # Aggregate per APN: a parcel may have many docs; ANY tax-deed doc
    # flags the parcel. Last-write-wins row-by-row would let a later
    # non-deed doc overwrite a real tax deed flag.
    parcels: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8-sig") as fp:
        for row in csv.DictReader(fp):
            apn = (row.get("apn") or "").strip()
            if not apn:
                continue
            grantors = (row.get("grantors") or "").upper()
            grantees = (row.get("grantees") or "").upper()
            dtype = (row.get("doc_type") or "").strip().upper()
            rec_date = (row.get("recording_date") or "").strip()
            # UNIVERSAL SIGNAL: the county tax collector appearing as a
            # party is the tax-deed test for every county — regardless of
            # doc type. Fresno proves doc-type whitelisting loses real
            # deeds (tax deeds come back as "T" *and* "C" certificates),
            # so no deed_like gate here.
            is_tax_deed = (
                cfg.is_county_holder(grantors)
                or cfg.is_county_holder(grantees)
                or "POWER TO SELL" in grantors)
            rec = parcels.get(apn, {"tax_deed": "no", "former_owner": "",
                                    "owner": "", "deed_date": ""})
            if is_tax_deed:
                # the tax-deed doc itself names the former owner (grantor)
                # and the buyer (grantee) — prefer its parties. The
                # recording date seeds the excess-proceeds escheat clock.
                rec["tax_deed"] = "yes"
                if cfg.is_county_holder(grantees):
                    # county took title: grantor is the true former owner.
                    # (Only set when a real owner is known, not the county.)
                    if grantors:
                        rec["former_owner"] = grantors.split("|")[0]
                    if grantees:
                        rec["owner"] = grantees.split("|")[0]
                else:
                    # county sold (or power-to-sell): buyer is the current
                    # owner; never let the county name clobber the former
                    # owner — that person holds the excess-proceeds claim.
                    if grantees:
                        rec["owner"] = grantees.split("|")[0]
                if rec_date and not rec["deed_date"]:
                    rec["deed_date"] = rec_date
            else:
                # non-deed docs still name parties; only fill if empty
                if not rec["former_owner"] and grantors:
                    rec["former_owner"] = grantors.split("|")[0]
                if not rec["owner"] and grantees:
                    rec["owner"] = grantees.split("|")[0]
            parcels[apn] = rec

    for apn, rec in parcels.items():
        store.upsert_parcel(apn, rec, commit=False)
        store.mark_known(apn, "tax_deed", commit=False)
        store.mark_known(apn, "former_owner", commit=False)
        store.mark_known(apn, "owner", commit=False)
        if rec.get("deed_date"):
            store.mark_known(apn, "deed_date", commit=False)
        counts["parcels_updated"] += 1
        if rec["tax_deed"] == "yes":
            counts["tax_deed"] += 1
    store.commit()
    print(f"[import:{cfg.county}] {counts['parcels_updated']:,} parcels "
          f"({counts['tax_deed']:,} tax deeds) -> state")
    if own_store:
        store.close()
    return counts
