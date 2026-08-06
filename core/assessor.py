"""
core/assessor.py

Unified assessor full-roll puller. One interface, multiple backends:

  arcgis   — paged REST query against a county GIS layer (Fresno, Shasta)
  mpts     — MPTS per-parcel / situs-discovery enumeration (Tehama)
  csv      — load an existing authoritative parcel index

Output is always the standard county roll (roll.csv): one row per parcel
with county, APN, situs, and any assessor fields available at the source.
"""
import csv
import time
from pathlib import Path

import requests

from .county import CountyConfig


def pull_roll(cfg: CountyConfig, out_path: Path | None = None) -> Path:
    out_path = out_path or cfg.roll_path()
    backend = cfg.assessor.backend
    if backend == "arcgis":
        return _pull_arcgis(cfg, out_path)
    if backend == "mpts":
        return _pull_mpts(cfg, out_path)
    if backend == "csv":
        return _load_csv(cfg, out_path)
    raise ValueError(f"Unknown assessor backend: {backend}")


def _headers():
    return {
        "User-Agent": (
            "LogicFlowSystems/1.0 (mrt@logicflowsystems.io) "
            "CA county tax auction intelligence"
        ),
        "Accept": "application/json",
    }


def _pull_arcgis(cfg: CountyConfig, out_path: Path) -> Path:
    endpoint = cfg.assessor.endpoint
    where = cfg.assessor.where
    page_size = 2000
    delay = 0.4

    def query(params: dict) -> dict:
        r = requests.get(endpoint, params=params, headers=_headers(), timeout=60)
        r.raise_for_status()
        return r.json()

    total = query({"where": where, "returnCountOnly": "true", "f": "json"}).get("count", 0)
    print(f"[assessor:{cfg.county}] ArcGIS full roll: {total:,} parcels")

    fieldnames = None
    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        writer = None
        offset = 0
        while offset < total:
            params = {
                "where": where,
                "outFields": cfg.assessor.out_fields,
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "returnGeometry": "false",
                "f": "json",
            }
            data = query(params)
            feats = data.get("features", [])
            if not feats:
                print(f"  empty batch at {offset} — stopping")
                break
            if writer is None:
                fieldnames = ["county"] + list(feats[0]["attributes"].keys())
                writer = csv.DictWriter(fp, fieldnames=fieldnames)
                writer.writeheader()
            for f in feats:
                row = {"county": cfg.county, **f["attributes"]}
                writer.writerow(row)
            offset += page_size
            print(f"  {offset:,} / {total:,} ({100*offset/total:.0f}%)", flush=True)
            time.sleep(delay)

    print(f"[assessor:{cfg.county}] wrote {out_path}")
    return out_path


def _pull_mpts(cfg: CountyConfig, out_path: Path) -> Path:
    """Enumerate via MPTS situs search using the configured seed queries."""
    base = cfg.assessor.endpoint.rstrip("/")
    slug = cfg.assessor.slug or cfg.county
    session = requests.Session()
    session.headers.update({
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
        "Referer": f"{base}/{slug}/tax/search",
    })
    seeds = cfg.assessor.apn_includes or ["1 Main", "2 Main", "Red Bluff", "Corning"]
    seen: dict[str, dict] = {}

    for q in seeds:
        try:
            r = session.get(
                f"{base}/api/search/{slug}/0000-CURR/situs/{requests.utils.quote(q)}",
                timeout=20,
            )
            if r.status_code != 200:
                print(f"  query '{q}' -> {r.status_code}")
                continue
            data = r.json()
            if isinstance(data, str):
                import json as _json
                data = _json.loads(data)
            rows = data.get("Table", {}).get("Row", [])
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows:
                apn = (row.get("FeeParcel") or row.get("Asmt") or "").replace("-", "")
                if apn:
                    seen.setdefault(apn, {"county": cfg.county, "apn": apn,
                                          "situs": row.get("Situs") or row.get("Address") or ""})
            print(f"  query '{q}': {len(rows)} rows ({len(seen):,} unique)")
        except Exception as e:
            print(f"  query '{q}' ERR: {type(e).__name__}: {str(e)[:80]}")
        time.sleep(0.3)

    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["county", "apn", "situs"])
        writer.writeheader()
        writer.writerows(seen.values())
    print(f"[assessor:{cfg.county}] MPTS discovery: {len(seen):,} parcels -> {out_path}")
    return out_path


def _load_csv(cfg: CountyConfig, out_path: Path) -> Path:
    src = Path(cfg.assessor.endpoint)
    if not src.exists():
        raise FileNotFoundError(f"Assessor csv source missing: {src}")
    import shutil
    shutil.copyfile(src, out_path)
    print(f"[assessor:{cfg.county}] copied existing roll {src} -> {out_path}")
    return out_path


def _mpts_apn_enrich(cfg: CountyConfig, apns: list[str],
                     delay: float = 0.15) -> list[dict]:
    """Per-APN enrichment from the MPTS assessor portal.

    Two page types across MPTS counties:
      - AsrPrint  (Tehama): full roll — values, situs, property type,
        acreage, current document number.
      - Tax bill  (Butte/Shasta): document number + tax balances.
    Either page yields the current document number — the lever into the
    recorder chain. Plain GET, no AJAX — fast enough to sweep a roll.
    """
    if not apns:
        return []
    import re
    from datetime import datetime
    slug = (cfg.assessor.slug or cfg.county).replace("-", "")
    host = re.sub(r"^https?://|/$", "", cfg.assessor.endpoint) if \
        (cfg.assessor.endpoint and cfg.assessor.endpoint.startswith("http")) \
        else "common1.mptsweb.com"
    year = str(datetime.now().year)
    records = []
    for apn in apns:
        asmt = apn.replace("-", "").strip()
        if not asmt:
            continue
        rec = {"APN": apn}
        got_any = False
        # 1) AsrPrint assessor page
        url = (f"https://{host}/mbap/{slug}/asr/"
               f"AsrPrint/{asmt}")
        try:
            r = requests.get(url, headers=_headers(), timeout=15)
            if r.status_code == 200:
                for tr in re.findall(r"<tr>.*?</tr>", r.text, re.S):
                    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
                    cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
                    if len(cells) < 2:
                        continue
                    label, value = cells[0], cells[1]
                    key = {
                        "SitusAddr": "SITEADDRESS1",
                        "Property Type": "USE_PRIMARY",
                        "Lot Size(Acres)": "ACREAGE",
                        "Lot Size(SqFt)": "SQFT",
                        "Current Document Number": "CURRENT_DOC_NUMBER",
                        "Net Assessed Value": "TOTAL_ASSESSED_VALUE",
                    }.get(label)
                    if key:
                        if key == "TOTAL_ASSESSED_VALUE":
                            value = re.sub(r"[^\d]", "", value)
                        if value:
                            got_any = True
                        rec[key] = value
        except Exception:
            pass
        # 2) Tax bill page for the document number if AsrPrint had none
        if not rec.get("CURRENT_DOC_NUMBER"):
            try:
                tax_url = (f"https://{host}/MBC/{slug}/tax/"
                           f"main/{asmt}/{year}/0000")
                r2 = requests.get(tax_url, headers=_headers(), timeout=15)
                if r2.status_code == 200:
                    # dt/dd layout (Glenn) or flat text (Butte/Shasta)
                    m = re.search(r"Document Number</dt>\s*<dd>([^<]*)</dd>",
                                  r2.text)
                    if not m:
                        txt = re.sub(r"<[^>]+>", " ", r2.text)
                        m = re.search(r"Document Number\s+([0-9A-Z]+)", txt)
                    if m:
                        rec["CURRENT_DOC_NUMBER"] = m.group(1).strip()
                        got_any = True
            except Exception:
                pass
        records.append(rec)
        time.sleep(delay)
    return records


def _arcgis_apn_enrich(cfg: CountyConfig, apns: list[str],
                       chunk: int = 200) -> list[dict]:
    """Per-APN enrichment from the ArcGIS assessor layer.

    Pulls full records for the given APNs (batched IN-queries). Returns the
    raw attribute dicts so the dynamic loop can store whatever fields the
    county provides.
    """
    if not apns:
        return []
    clean = [a.replace("-", "").strip() for a in apns if a and a.strip()]
    # preserve suffixed APNs (e.g. 08018018S) — IN clause handles them
    records = []
    apn_field = cfg.assessor.apn_field
    for i in range(0, len(clean), chunk):
        batch = clean[i:i + chunk]
        quoted = ", ".join(f"'{a}'" for a in batch)
        params = {
            "where": f"{apn_field} IN ({quoted})",
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
        }
        r = requests.get(cfg.assessor.endpoint, params=params,
                         headers=_headers(), timeout=60)
        r.raise_for_status()
        records.extend(f["attributes"] for f in r.json().get("features", []))
        time.sleep(0.3)
    return records

