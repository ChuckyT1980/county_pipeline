"""onboard_county.py — auto-discovery onboarding for a CA county.

Finds, verifies, and writes counties/<name>.yaml:

  1. Assessor — probe MPTS hosts (common1/2/3.mptsweb.com) x slug
     candidates for a live tax-search page (marker: FeeParcel).
  2. Recorder — probe candidate Tyler Self-Service portal hostnames;
     on a hit run the full discovery chain:
        playwright loads the JS menu -> ACTIONGROUP ids
        -> httpx reads each group page -> DOCSEARCH ids
        -> each search page's form fields classify it:
             field_BothNamesID        -> name search
             field_DocumentNumberID   -> doc-number search
             field_ParcelID           -> APN search
             field_RecordingDateID + documentTypes -> type+date (radar)
  3. Collector names + GovEase auction placeholder.

Usage:
  python onboard_county.py --county glenn            # discover + write yaml
  python onboard_county.py --county glenn --dry      # discover, no write
  python onboard_county.py --all-scan                # coverage map, no write
  python onboard_county.py --all                     # discover + write all
"""
import argparse
import concurrent.futures as cf
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
COUNTIES_DIR = ROOT / "counties"
TAX_CFG = None
try:
    from tax_pipeline import config as _tp
    TAX_CFG = _tp.COUNTY_CONFIG
except Exception:
    TAX_CFG = {}

CA_COUNTIES = [
    "alameda", "alpine", "amador", "butte", "calaveras", "colusa",
    "contra_costa", "del_norte", "el_dorado", "fresno", "glenn", "humboldt",
    "imperial", "inyo", "kern", "kings", "lake", "lassen", "los_angeles",
    "madera", "marin", "mariposa", "mendocino", "merced", "modoc", "mono",
    "monterey", "napa", "nevada", "orange", "placer", "plumas", "riverside",
    "sacramento", "san_benito", "san_bernardino", "san_diego",
    "san_francisco", "san_joaquin", "san_luis_obispo", "san_mateo",
    "santa_barbara", "santa_clara", "santa_cruz", "shasta", "sierra",
    "siskiyou", "solano", "sonoma", "stanislaus", "sutter", "tehama",
    "trinity", "tulare", "tuolumne", "ventura", "yolo", "yuba",
]

MPTS_HOSTS = ["common1.mptsweb.com", "common2.mptsweb.com",
              "common3.mptsweb.com"]
TYLER_MARKERS = ["/web/user/disclaimer", "DOCSEARCH", "Self-Service Web"]


def slug_variants(name: str) -> list[str]:
    """MPTS/Tyler slug candidates for a county name."""
    out = [name, name.replace("_", "")]
    cfg = TAX_CFG.get(name)
    if cfg and cfg.get("county_slug"):
        out.append(cfg["county_slug"])
    return list(dict.fromkeys(out))


def mpts_candidates(name: str) -> list[tuple[str, str]]:
    pairs = []
    cfg = TAX_CFG.get(name)
    if cfg and cfg.get("host"):
        host = cfg["host"].replace("https://", "")
        pairs.append((host, cfg.get("county_slug") or name))
    for host in MPTS_HOSTS:
        for slug in slug_variants(name):
            pairs.append((host, slug))
    return list(dict.fromkeys(pairs))


def tyler_candidates(name: str) -> list[str]:
    urls = []
    for slug in slug_variants(name):
        urls += [
            f"https://recordsearch.{slug}.gov",
            f"https://recordsearch.{slug}county.gov",
            f"https://recorderselfservice.{slug}county.gov",
            f"https://recorder.{slug}county.net",
            f"https://recordsearch.{slug}county.net",
            f"https://{slug}-web.tylerhost.net",
            f"https://{slug}countyca-web.tylerhost.net",
        ]
    return list(dict.fromkeys(urls))


def probe_mpts(host: str, slug: str) -> tuple[str, str] | None:
    try:
        r = httpx.get(f"https://{host}/MBC/{slug}/tax/search",
                      follow_redirects=True, timeout=12,
                      headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and "FeeParcel" in r.text:
            return host, slug
    except Exception:
        pass
    return None


def probe_tyler(url: str) -> str | None:
    try:
        r = httpx.get(f"{url}/web/user/disclaimer",
                      follow_redirects=True, timeout=12,
                      headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and any(m in r.text for m in TYLER_MARKERS):
            return url.rstrip("/")
    except Exception:
        pass
    return None


def tyler_session(base: str) -> httpx.Client:
    s = httpx.Client(follow_redirects=True, timeout=30)
    try:
        s.get(f"{base}/web/user/disclaimer")
        s.post(f"{base}/web/user/disclaimer", data={})
    except Exception:
        pass
    return s


def discover_search_ids(base: str) -> dict:
    """The discovery chain: JS menu -> ACTIONGROUP -> DOCSEARCH ids."""
    found = {"base_url": base}
    doc_ids: list[str] = []
    try:
        import asyncio
        from playwright.async_api import async_playwright

        async def scrape_menu():
            async with async_playwright() as p:
                b = await p.chromium.launch(headless=True)
                pg = await b.new_page()
                try:
                    await pg.request.post(f"{base}/web/user/disclaimer",
                                          data={})
                    await pg.goto(f"{base}/web/", timeout=30000)
                    await pg.wait_for_timeout(6000)
                    links = await pg.eval_on_selector_all(
                        "a", "els => els.map(e => e.getAttribute('href'))")
                    await b.close()
                    return [h for h in links if h]
                except Exception as e:
                    await b.close()
                    return []

        links = asyncio.run(scrape_menu())
    except Exception as e:
        print(f"  [tyler] playwright failed: {str(e)[:80]}")
        links = []
    group_ids = sorted({re.sub(r".*/action/", "", h) for h in links
                        if "/action/" in h and re.search(r"ACTIONGROUP\d+S\d+", h)})
    for g in group_ids:
        try:
            s = tyler_session(base)
            r = s.get(f"{base}/web/action/{g}")
            doc_ids += re.findall(r"DOCSEARCH\d+S\d+", r.text)
        except Exception:
            pass
    s = tyler_session(base)
    fields_map: dict[str, set] = {}
    for sid in sorted(set(doc_ids)):
        try:
            r = s.get(f"{base}/web/search/{sid}")
            fields_map[sid] = set(re.findall(r'name="(field_[^"]+)"', r.text))
        except Exception:
            fields_map[sid] = set()
    classified = {sid: fs for sid, fs in fields_map.items() if fs}
    found["searches"] = classified
    # two field-name dialects seen live: Tehama (field_DocumentNumberID,
    # field_RecordingDateID_...) and Glenn (field_DocNumID,
    # field_RecDateID_...)
    def has(fs, *names):
        return any(n in fs for n in names)
    for sid, fs in classified.items():
        if has(fs, "field_BothNamesID") and not found.get("name_search_id"):
            found["name_search_id"] = sid
        if has(fs, "field_DocumentNumberID", "field_DocNumID") \
                and not found.get("doc_search_id"):
            found["doc_search_id"] = sid
            found["doc_field"] = ("field_DocumentNumberID"
                                  if "field_DocumentNumberID" in fs
                                  else "field_DocNumID")
        if has(fs, "field_ParcelID") and not found.get("apn_search_id"):
            found["apn_search_id"] = sid
    # the type+date radar wants the search WITHOUT a name field — a bare
    # doc-type + recording-date query costs one call per county, not one
    # per name
    for sid, fs in classified.items():
        if (sid == found.get("name_search_id")
                and "field_BothNamesID" in fs):
            continue
        if (has(fs, "field_RecordingDateID_DOT_StartDate",
                 "field_RecDateID_DOT_StartDate")
                and "field_selfservice_documentTypes" in fs
                and not found.get("typedate_search_id")):
            found["typedate_search_id"] = sid
    return found


def collector_names(name: str) -> list[str]:
    upper = name.replace("_", " ").upper()
    short = name.replace("_", " ").upper().replace(" COUNTY", "")
    return [f"{upper} TAX COLLECTOR",
            f"{short} CO TAX COLLR",
            f"COUNTY OF {short}"]


def write_yaml(name: str, mpts: tuple | None, tyler: dict, dry: bool) -> Path | None:
    display = " ".join(w.capitalize() for w in name.split("_"))
    lines = [f"display_name: {display} County", "collector_names:"]
    for c in collector_names(name):
        lines.append(f"  - \"{c}\"")
    notes = "Auto-onboarded by onboard_county.py."
    if mpts:
        host, slug = mpts
        lines += ["", "assessor:", "  backend: mpts",
                  f"  endpoint: https://{host}/MBC"]
        if slug != name:
            lines.append(f"  slug: {slug}")
        lines += ["  apn_includes: [\"1 Main\", \"2 Main\", \"1 Oak\", "
                  "\"2 Oak\", \"1 Pine\", \"1st\", \"2nd\", \"3rd\"]",
                  f"  notes: {notes} MPTS host {host} slug {slug}"]
    else:
        lines += ["", "assessor:", "  backend: manual",
                  "  notes: no public assessor source discovered yet"]
    if tyler.get("base_url"):
        lines += ["", "recorder:", "  backend: tyler",
                  f"  base_url: {tyler['base_url']}",
                  f"  name_search_id: {tyler.get('name_search_id') or ''}",
                  f"  doc_search_id: {tyler.get('doc_search_id') or ''}",
                  f"  apn_search_id: {tyler.get('apn_search_id') or ''}",
                  f"  typedate_search_id: {tyler.get('typedate_search_id') or ''}",
                  "  ajax_headers_required: true",
                  "  notes: discovered automatically"]
        if tyler.get("doc_field") and tyler["doc_field"] != "field_DocumentNumberID":
            lines.append(f"  doc_field: {tyler['doc_field']}")
    else:
        lines += ["", "recorder:", "  backend: manual",
                  "  notes: no Tyler portal discovered"]
    lines += ["", "auction:", "  backend: govease", "  base_url: \"\"",
              "  preview_url: \"\""]
    lines.append("")
    body = "\n".join(lines)
    path = COUNTIES_DIR / f"{name}.yaml"
    if dry:
        print(body)
        return None
    path.write_text(body, encoding="utf-8")
    print(f"[onboard] wrote {path}")
    return path


def discover_county(name: str, workers: int = 12) -> dict:
    print(f"== {name} ==")
    res = {"county": name, "mpts": None, "tyler": {}}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        mpts_hits = [f for f in ex.map(
            lambda c: probe_mpts(*c), mpts_candidates(name)) if f]
    if mpts_hits:
        res["mpts"] = mpts_hits[0]
        print(f"  [mpts] {res['mpts'][0]} / {res['mpts'][1]}")
    else:
        print("  [mpts] none")
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        tyler_hits = [u for u in ex.map(probe_tyler, tyler_candidates(name))
                      if u]
    if tyler_hits:
        base = tyler_hits[0]
        print(f"  [tyler] {base}")
        res["tyler"] = discover_search_ids(base)
        found = [k for k in ("name_search_id", "doc_search_id",
                             "apn_search_id", "typedate_search_id")
                 if res["tyler"].get(k)]
        print(f"  [tyler] searches: {found}")
    if not res["tyler"].get("base_url"):
        print("  [tyler] none")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Auto-discovery county onboarding")
    ap.add_argument("--county", help="county name, e.g. glenn")
    ap.add_argument("--dry", action="store_true", help="discover but don't write")
    ap.add_argument("--all", action="store_true", help="discover + write every county")
    ap.add_argument("--all-scan", action="store_true",
                    help="coverage map only (no yaml writes)")
    args = ap.parse_args(argv)

    if args.all or args.all_scan:
        names = [c for c in CA_COUNTIES
                 if not (COUNTIES_DIR / f"{c}.yaml").exists()] if args.all \
            else CA_COUNTIES
        results = {}
        for name in names:
            results[name] = discover_county(name)
            print()
        print("===== COVERAGE MAP =====")
        print(f"{'county':<16}{'mpts':<12}{'tyler portal':<48}searches")
        for name in sorted(results):
            r = results[name]
            mpts = f"{r['mpts'][0].split('.')[0]}/{r['mpts'][1]}" if r["mpts"] else "-"
            t = r["tyler"].get("base_url", "-")
            sids = "+".join(sorted(k.replace("_search_id", "") for k in
                                   ("name_search_id", "doc_search_id",
                                    "apn_search_id", "typedate_search_id")
                                   if r["tyler"].get(k))) or "-"
            print(f"{name:<16}{mpts:<12}{t:<48}{sids}")
        if args.all:
            for name, r in results.items():
                write_yaml(name, r["mpts"], r["tyler"], dry=False)
        return 0

    if not args.county:
        ap.error("pass --county NAME, --all, or --all-scan")
    name = args.county.strip().lower()
    r = discover_county(name)
    write_yaml(name, r["mpts"], r["tyler"], dry=args.dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
